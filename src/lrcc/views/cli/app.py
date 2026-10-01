"""The ``lrcc`` command: parses arguments, calls a feature, renders its result (ADR-0003).

Nothing here decides anything. Every rule lives in a feature or in the domain, and
``tests/test_layering.py`` names any function here that does work without presenting it.

Values that come from files, such as titles and paths, are rendered as plain ``Text``, never
as Rich markup, so a title containing ``[bold]`` is printed as written.
"""

import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from lrcc.domain.errors import LrccError
from lrcc.features.check_query import CheckResult, GoldState, check_query
from lrcc.features.configuration import (
    CONFIG_ENV,
    load_settings,
    open_configured_workspace,
    workspace_of,
)
from lrcc.features.dedupe import DedupeResult, dedupe_review
from lrcc.features.imports import ImportOutcome, import_run
from lrcc.features.init import InitResult, init_review
from lrcc.features.replay import ReplayResult, replay_review
from lrcc.features.search import RunOutcome, SearchOutcome, run_search, search_review
from lrcc.features.status import StatusResult, review_status
from lrcc.features.validate import ValidationResult, validate_review
from lrcc.features.verify import VerifyResult, verify_review
from lrcc.views.cli.composition import build_catalog, build_source, build_sources, build_store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="LRCC, the Literature Review Control Center.",
)
console = Console(highlight=False, soft_wrap=True)
errors = Console(stderr=True, highlight=False, soft_wrap=True)

ReviewIdArgument = Annotated[
    str,
    typer.Argument(
        help="The review's id: lowercase letters, digits and hyphens.", show_default=False
    ),
]
ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        envvar=CONFIG_ENV,
        help=f"The configuration file. Defaults to the {CONFIG_ENV} environment variable.",
        show_default=False,
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Print the result as JSON.")]


class SourceName(StrEnum):
    """The sources the commands offer. A test keeps it equal to the adapters that exist."""

    arxiv = "arxiv"
    ieee = "ieee"
    pubmed = "pubmed"
    scopus = "scopus"


SourceOption = Annotated[
    SourceName, typer.Option("--source", help="The source to search.", show_default=False)
]
LimitOption = Annotated[
    int | None,
    typer.Option(
        "--limit",
        min=1,
        max=10000,
        help="The most records to retrieve. Defaults to all for a run, and a few for a preview.",
        show_default=False,
    ),
]
PreviewOption = Annotated[
    bool, typer.Option("--preview", help="Show what the string returns, and store nothing.")
]
ExportSourceOption = Annotated[
    SourceName,
    typer.Option("--source", help="The source the files were exported from.", show_default=False),
]
ExportFilesArgument = Annotated[
    list[Path],
    typer.Argument(
        help="The RIS file(s) the database exported for one search, in the order exported.",
        show_default=False,
    ),
]
SearchedOption = Annotated[
    datetime,
    typer.Option(
        "--searched",
        formats=["%Y-%m-%d"],
        help="The day the search was run in the database, as YYYY-MM-DD.",
        show_default=False,
    ),
]
ReportedOption = Annotated[
    int,
    typer.Option(
        "--reported",
        min=0,
        help="The count of records the database reported for the search.",
        show_default=False,
    ),
]


@app.command()
def init(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """Create a review in the workspace, with a protocol template to fill in."""
    try:
        result = init_review(open_configured_workspace(config, os.environ), review_id)
    except LrccError as error:
        _fail(error, as_json)
    if as_json:
        _echo_json(result.as_dict())
    else:
        _show_init(result)


@app.command()
def validate(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """Check a review's protocol and print its SHA-256, the digest to register."""
    try:
        result = validate_review(open_configured_workspace(config, os.environ), review_id)
    except LrccError as error:
        _fail(error, as_json)
    if as_json:
        _echo_json(result.as_dict())
    else:
        _show_validation(result)


@app.command()
def search(
    review_id: ReviewIdArgument,
    source: SourceOption,
    preview: PreviewOption = False,
    limit: LimitOption = None,
    config: ConfigOption = None,
    as_json: JsonOption = False,
) -> None:
    """Run the protocol's search string on one source and store the run, or preview it."""
    try:
        settings = load_settings(config, os.environ)
        workspace = workspace_of(settings.config, os.environ)
        chosen = build_source(source.value, settings.config, settings.secrets)
        if preview:
            outcome = search_review(workspace, review_id, chosen, limit)
            _present(outcome.as_dict(), as_json, lambda: _show_search(outcome))
        else:
            stored = run_search(
                workspace, review_id, chosen, build_store(workspace, review_id), limit
            )
            _present(stored.as_dict(), as_json, lambda: _show_run(stored))
    except LrccError as error:
        _fail(error, as_json)


@app.command("import")
def import_command(
    review_id: ReviewIdArgument,
    files: ExportFilesArgument,
    source: ExportSourceOption,
    searched: SearchedOption,
    reported: ReportedOption,
    config: ConfigOption = None,
    as_json: JsonOption = False,
) -> None:
    """Store a database's RIS export of the protocol's string as a run of that source."""
    try:
        workspace = open_configured_workspace(config, os.environ)
        outcome = import_run(
            workspace,
            review_id,
            source.value,
            files,
            searched.date(),
            reported,
            build_store(workspace, review_id),
        )
    except LrccError as error:
        _fail(error, as_json)
    _present(outcome.as_dict(), as_json, lambda: _show_import(outcome))


@app.command()
def status(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """List a review's stored runs, and check its run log. Exits 1 if the log was edited."""
    try:
        workspace = open_configured_workspace(config, os.environ)
        result = review_status(workspace, review_id, build_store(workspace, review_id))
    except LrccError as error:
        _fail(error, as_json)
    _present(result.as_dict(), as_json, lambda: _show_status(result))
    if result.chain_problems:
        raise typer.Exit(code=1)


@app.command()
def verify(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """Check every stored response and record against the run log. Exits 1 on any mismatch."""
    try:
        workspace = open_configured_workspace(config, os.environ)
        result = verify_review(workspace, review_id, build_store(workspace, review_id))
    except LrccError as error:
        _fail(error, as_json)
    _present(result.as_dict(), as_json, lambda: _show_verify(result))
    if result.problems:
        raise typer.Exit(code=1)


@app.command()
def replay(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """Rederive every run's records from its stored responses, offline. Exits 1 if any differ."""
    try:
        settings = load_settings(config, os.environ)
        workspace = workspace_of(settings.config, os.environ)
        result = replay_review(
            workspace,
            review_id,
            build_store(workspace, review_id),
            build_sources(settings.config, settings.secrets),
        )
    except LrccError as error:
        _fail(error, as_json)
    _present(result.as_dict(), as_json, lambda: _show_replay(result))
    if not result.identical:
        raise typer.Exit(code=1)


def _show_verify(result: VerifyResult) -> None:
    console.print(
        Text.assemble(
            "Review ",
            (result.review_id, "bold"),
            f": {result.runs} run(s) and {result.responses} stored response(s) checked.",
        )
    )
    if result.problems:
        console.print(Text("What is stored does not match the log:", style="bold red"))
        for problem in result.problems:
            console.print(Text(f"  - {problem}"))
    else:
        console.print(Text("Everything stored matches the log.", style="green"))


def _show_replay(result: ReplayResult) -> None:
    console.print(Text.assemble("Review ", (result.review_id, "bold"), ", replayed offline."))
    if not result.runs:
        console.print(Text("  No runs are stored yet."))
    for run in result.runs:
        replayed = "-" if run.replayed is None else str(run.replayed)
        verdict = "identical" if run.identical else f"DIFFERENT: {run.problem}"
        console.print(Text(f"  {run.run_id}  logged {run.logged}  replayed {replayed}  {verdict}"))
    if result.runs and result.identical:
        console.print(Text("Every run is reproduced from its stored responses.", style="green"))


@app.command()
def dedupe(
    review_id: ReviewIdArgument, config: ConfigOption = None, as_json: JsonOption = False
) -> None:
    """Join the review's records into works through shared identifiers: exact duplicates."""
    try:
        workspace = open_configured_workspace(config, os.environ)
        result = dedupe_review(
            workspace, review_id, build_store(workspace, review_id), build_catalog(workspace)
        )
    except LrccError as error:
        _fail(error, as_json)
    _present(result.as_dict(), as_json, lambda: _show_dedupe(result))


def _show_dedupe(result: DedupeResult) -> None:
    console.print(
        Text.assemble(
            "Review ",
            (result.review_id, "bold"),
            f": {result.linked_now} record(s) linked to works in this pass.",
        )
    )
    if result.joined_by:
        joined = ", ".join(f"{kind} {count}" for kind, count in sorted(result.joined_by.items()))
        console.print(Text(f"  joined a work already named, by: {joined}"))
    # One line per run, never a table: a run id must stay whole to be copied or searched for.
    for run in result.runs:
        console.print(
            Text(
                f"  {run.run_id}  {run.records} records  {run.first_seen} first seen  "
                f"{run.already_seen} already seen  "
                f"protocol {'current' if run.current_protocol else 'changed since'}"
            )
        )
    console.print(
        Text(
            f"Runs under the current protocol: {result.current_records} records,"
            f" {result.current_works} works, {result.current_duplicates} duplicates removed.",
            style="green",
        )
    )
    console.print(
        Text(
            f"The review holds {result.works} works. {result.unstable} of them are named from a"
            " title or a database's own number, not from a DOI, PMID or arXiv id."
        )
    )


@app.command("check-query")
def check_query_command(
    review_id: ReviewIdArgument,
    source: SourceOption,
    config: ConfigOption = None,
    as_json: JsonOption = False,
) -> None:
    """Test the protocol's string against the gold set. Exits 1 if it misses an indexed work."""
    try:
        settings = load_settings(config, os.environ)
        result = check_query(
            workspace_of(settings.config, os.environ),
            review_id,
            build_source(source.value, settings.config, settings.secrets),
        )
    except LrccError as error:
        _fail(error, as_json)
    _present(result.as_dict(), as_json, lambda: _show_check(result))
    if not result.complete:
        raise typer.Exit(code=1)


def _show_check(result: CheckResult) -> None:
    console.print(
        Text.assemble(
            "Gold set of ",
            (result.review_id, "bold"),
            f": {len(result.checks)} work(s) checked against the {result.source} string.",
        )
    )
    for state, meaning in (
        (GoldState.retrieved, "the string finds them"),
        (GoldState.missed, "indexed, but the string misses them"),
        (GoldState.not_indexed, f"not held by {result.source}: coverage, not the string"),
        (GoldState.unknown, f"no identifier {result.source} can look up"),
    ):
        console.print(Text(f"  {result.count(state):>3}  {state.value:<12} {meaning}"))
    for state in (GoldState.missed, GoldState.not_indexed, GoldState.unknown):
        works = [check.work for check in result.checks if check.state is state]
        if works:
            console.print(Text(f"{state.value.capitalize()}:", style="bold"))
            for work in works:
                console.print(Text(f"  - {work.label}  ({work.identifiers})"))
    if result.complete:
        console.print(
            Text("The string retrieves every gold work this source holds.", style="green")
        )
    else:
        console.print(Text("The string misses gold works this source holds.", style="bold red"))


def _present(data: Mapping[str, object], as_json: bool, show: Callable[[], None]) -> None:
    if as_json:
        _echo_json(data)
    else:
        show()


def _show_run(outcome: RunOutcome) -> None:
    run = outcome.logged.run
    console.print(Text.assemble("Stored run ", (run.run_id, "bold"), "."))
    for label, value in (
        ("source", run.source),
        ("reported", str(run.reported)),
        ("retrieved", str(run.retrieved)),
        ("responses", f"{len(run.responses)} file(s) under runs/{run.run_id}"),
        ("protocol", run.protocol_sha256),
        ("entry hash", outcome.logged.entry_hash),
    ):
        console.print(Text(f"  {label:<11}{value}"))
    if not run.complete:
        console.print(
            Text(
                f"Incomplete: {run.source} reports {run.reported} records and"
                f" {run.retrieved} were retrieved.",
                style="yellow",
            )
        )


def _show_import(outcome: ImportOutcome) -> None:
    run = outcome.logged.run
    console.print(Text.assemble("Stored run ", (run.run_id, "bold"), ", imported from an export."))
    for label, value in (
        ("source", run.source),
        ("searched", run.searched_on),
        ("reported", str(run.reported)),
        ("imported", str(run.retrieved)),
        ("files", f"{len(run.responses)} file(s) under runs/{run.run_id}"),
        ("protocol", run.protocol_sha256),
        ("entry hash", outcome.logged.entry_hash),
    ):
        console.print(Text(f"  {label:<11}{value}"))
    if not run.complete:
        console.print(
            Text(
                f"Incomplete: {run.source} reported {run.reported} records and the files hold"
                f" {run.retrieved}.",
                style="yellow",
            )
        )


def _show_status(result: StatusResult) -> None:
    console.print(Text.assemble("Review ", (result.review_id, "bold"), "."))
    console.print(Text(f"  protocol   {result.protocol_sha256}"))
    if not result.runs:
        console.print(Text("  No runs are stored yet."))
    # One line per run, never a table: a run id must stay whole to be copied or searched for.
    for summary in result.runs:
        run = summary.logged.run
        origin = f"export searched {run.searched_on}  " if run.imported else ""
        console.print(
            Text(
                f"  {run.run_id}  {origin}reported {run.reported}  retrieved {run.retrieved}  "
                f"{'complete' if run.complete else 'incomplete'}  "
                f"protocol {'current' if summary.current_protocol else 'changed since'}"
            )
        )
    if result.chain_problems:
        console.print(Text("The run log does not verify:", style="bold red"))
        for problem in result.chain_problems:
            console.print(Text(f"  - {problem}"))
    else:
        console.print(Text("The run log verifies: no entry was edited.", style="green"))


def _show_search(outcome: SearchOutcome) -> None:
    result = outcome.result
    console.print(
        Text.assemble(
            (result.source, "bold"),
            f" reports {result.reported} records for the search string of ",
            (outcome.review_id, "bold"),
            f"; {len(result.records)} retrieved.",
        )
    )
    table = Table(show_lines=False)
    for column in ("id", "year", "first author", "title"):
        table.add_column(column)
    for record in result.records:
        table.add_row(
            Text(record.source_id),
            Text(str(record.year) if record.year else "-"),
            Text(record.authors[0] if record.authors else "-"),
            Text(record.title),
        )
    if result.records:
        console.print(table)
    console.print(Text("Nothing was stored: this is a preview, not a run.", style="yellow"))


def _show_init(result: InitResult) -> None:
    console.print(Text.assemble("Created review ", (result.review_id, "bold"), "."))
    console.print(Text(f"  protocol  {result.protocol}"))
    console.print(Text(f"  sha256    {result.sha256}"))
    console.print(
        Text(f"Next: replace the synthetic example, then run: lrcc validate {result.review_id}")
    )


def _show_validation(result: ValidationResult) -> None:
    console.print(
        Text.assemble("The protocol of ", (result.review_id, "bold"), " is valid.", style="green")
    )
    for label, value in (
        ("title", result.title),
        ("inclusion", ", ".join(result.inclusion)),
        ("exclusion", ", ".join(result.exclusion)),
        ("sources", ", ".join(result.sources)),
        ("extraction", ", ".join(result.extraction)),
        ("protocol", str(result.protocol)),
        ("sha256", result.sha256),
    ):
        console.print(Text(f"  {label:<11}{value}"))


def _echo_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=True))


def _fail(error: LrccError, as_json: bool) -> NoReturn:
    if as_json:
        _echo_json({"error": error.message, "details": list(error.details)})
    else:
        errors.print(Text.assemble(("error: ", "bold red"), error.message))
        for detail in error.details:
            errors.print(Text(f"  - {detail}"))
    raise typer.Exit(code=1)


def main() -> None:
    """Run the ``lrcc`` command."""
    app()
