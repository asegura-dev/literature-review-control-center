"""The ``lrcc`` command: parses arguments, calls a feature, renders its result (ADR-0003).

Nothing here decides anything. Every rule lives in a feature or in the domain, and
``tests/test_layering.py`` names any function here that does work without presenting it.

Values that come from files, such as titles and paths, are rendered as plain ``Text``, never
as Rich markup, so a title containing ``[bold]`` is printed as written.
"""

import json
import os
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
from lrcc.features.search import SearchOutcome, search_review
from lrcc.features.validate import ValidationResult, validate_review
from lrcc.views.cli.composition import build_source

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
    int, typer.Option("--limit", min=1, max=10000, help="The most records to retrieve.")
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
    limit: LimitOption = 20,
    config: ConfigOption = None,
    as_json: JsonOption = False,
) -> None:
    """Run the protocol's search string on one source, as a preview. Nothing is stored."""
    try:
        configuration = load_configuration(config)
        outcome = search_review(
            workspace_of(configuration, os.environ),
            review_id,
            build_source(source.value, configuration),
            limit,
        )
    except LrccError as error:
        _fail(error, as_json)
    if as_json:
        _echo_json(outcome.as_dict())
    else:
        _show_search(outcome)


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
