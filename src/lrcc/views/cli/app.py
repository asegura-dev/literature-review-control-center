"""The ``lrcc`` command: parses arguments, calls a feature, renders its result (ADR-0003).

Nothing here decides anything. Every rule lives in a feature or in the domain, and
``tests/test_layering.py`` names any function here that does work without presenting it.

Values that come from files, such as titles and paths, are rendered as plain ``Text``, never
as Rich markup, so a title containing ``[bold]`` is printed as written.
"""

import json
import os
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.text import Text

from lrcc.domain.errors import LrccError
from lrcc.features.configuration import CONFIG_ENV, open_configured_workspace
from lrcc.features.init import InitResult, init_review
from lrcc.features.validate import ValidationResult, validate_review

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
