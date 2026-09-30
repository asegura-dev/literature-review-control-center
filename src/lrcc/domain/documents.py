"""YAML documents written by people, read into a mapping once, at the boundary.

Configuration files and protocols are YAML. ``yaml.safe_load`` builds only plain data, never
Python objects, so a file cannot run code however it is written (ADR-0010).
"""

from __future__ import annotations

from typing import Annotated

import yaml
from pydantic import StringConstraints

from lrcc.domain.errors import LrccError

#: A required piece of text: surrounding whitespace is ignored, and nothing left is an error.
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def load_mapping(text: str, source: str, error: type[LrccError]) -> dict[str, object]:
    """Parse ``text`` as a YAML mapping.

    Args:
        text: The document.
        source: Where it came from, named in any error.
        error: The error type to raise, so each caller reports in its own terms.

    Returns:
        The top-level mapping of the document.

    Raises:
        LrccError: As ``error``, if the document is not YAML, is empty, or is not a mapping.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as problem:
        raise error(f"{source} is not valid YAML", [_where(problem)]) from None
    if data is None:
        raise error(f"{source} is empty")
    if not isinstance(data, dict):
        raise error(f"{source} must be a mapping of fields, not a {type(data).__name__}")
    return data


def _where(problem: yaml.YAMLError) -> str:
    if isinstance(problem, yaml.MarkedYAMLError) and problem.problem_mark is not None:
        mark = problem.problem_mark
        return f"line {mark.line + 1}, column {mark.column + 1}: {problem.problem}"
    return str(problem)
