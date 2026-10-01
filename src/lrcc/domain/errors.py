"""Errors a person can act on, and validation failures turned into plain lines.

Every error LRCC reports to a person derives from :class:`LrccError`. It carries one sentence
saying what went wrong and, optionally, details saying where or what to do. A view can print it
without a traceback, and ``--json`` returns the same content as data (ADR-0010).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError
from pydantic_core import ErrorDetails


class LrccError(Exception):
    """An error with a message a person can act on."""

    def __init__(self, message: str, details: Sequence[str] = ()) -> None:
        """Create the error.

        Args:
            message: One sentence saying what went wrong.
            details: Lines saying where, or what to do about it.
        """
        super().__init__(message)
        self.message = message
        self.details = tuple(details)


class ConfigError(LrccError):
    """The configuration is missing, unreadable or invalid."""


class ProtocolError(LrccError):
    """A review protocol is unreadable or invalid."""


class WorkspaceError(LrccError):
    """The workspace is refused, or a path escapes it (ADR-0006)."""


class ReviewError(LrccError):
    """A review id is invalid, or the review is not where it should be."""


class NetworkError(LrccError):
    """A request was refused before it was sent, or a host did not answer (ADR-0011)."""


class SourceError(LrccError):
    """A source answered with something LRCC cannot read as records."""


class StoreError(LrccError):
    """A review's database or its stored responses could not be read or written (ADR-0012)."""


class DedupeError(LrccError):
    """Records cannot be joined into works without a person's decision (ADR-0017)."""


def describe_validation(error: ValidationError) -> list[str]:
    """Turn a Pydantic validation error into one plain line per problem.

    Args:
        error: The error raised while validating data that came from outside.

    Returns:
        One line per problem, such as ``criteria.0.code: must look like INC1 or EXC1``.
    """
    lines = []
    for problem in error.errors():
        where = ".".join(str(part) for part in problem["loc"]) or "(top level)"
        lines.append(f"{where}: {_explain(problem)}")
    return lines


def _explain(problem: ErrorDetails) -> str:
    kind = problem["type"]
    context = problem.get("ctx", {})
    if kind == "missing":
        return "is required"
    if kind == "extra_forbidden":
        return "is not a known field"
    # A key written with nothing after it (`title:`) arrives as None, whatever type was expected.
    if problem.get("input", ...) is None or kind == "string_too_short":
        return "must not be empty"
    if kind == "too_short":
        return "must have at least one entry"
    if kind == "literal_error":
        return f"must be {context.get('expected')}"
    if kind == "value_error":
        return str(context.get("error"))
    return problem["msg"]
