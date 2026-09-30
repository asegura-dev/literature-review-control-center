"""The ``lrcc`` command: parses arguments, calls a feature, renders its result (ADR-0003).

Nothing here decides anything. Every rule lives in a feature or in the domain, and
``tests/test_layering.py`` names any function here that does work without presenting it.

Values that come from files, such as titles and paths, are rendered as plain ``Text``, never
as Rich markup, so a title containing ``[bold]`` is printed as written.
"""

import json
import os
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from lrcc.domain.errors import LrccError
from lrcc.features.configuration import (
    CONFIG_ENV,
    load_configuration,
    open_configured_workspace,
    workspace_of,
)
from lrcc.features.init import InitResult, init_review
from lrcc.features.search import RunOutcome, SearchOutcome, run_search, search_review
from lrcc.features.status import StatusResult, review_status
from lrcc.features.validate import ValidationResult, validate_review
from lrcc.views.cli.composition import build_source, build_store

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
    """The sources ``lrcc search`` offers. A test keeps it equal to the adapters that exist."""

    arxiv = "arxiv"
    pubmed = "pubmed"


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
        configuration = load_configuration(config)
        workspace = workspace_of(configuration, os.environ)
        chosen = build_source(source.value, configuration)
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


def _show_status(result: StatusResult) -> None:
    console.print(Text.assemble("Review ", (result.review_id, "bold"), "."))
    console.print(Text(f"  protocol   {result.protocol_sha256}"))
    if not result.runs:
        console.print(Text("  No runs are stored yet."))
    # One line per run, never a table: a run id must stay whole to be copied or searched for.
    for summary in result.runs:
        run = summary.logged.run
        console.print(
            Text(
                f"  {run.run_id}  reported {run.reported}  retrieved {run.retrieved}  "
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
