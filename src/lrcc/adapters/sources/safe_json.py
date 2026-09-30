"""Reading the JSON sources answer with, without trusting its shape (ADR-0015).

An answer is data from outside. It is parsed once, and every field is read through a helper
that returns an empty value when the field is missing or has an unexpected type. Anything that
must be there, such as a count or an identifier, is then checked by the adapter.
"""

from __future__ import annotations

import json

from lrcc.adapters.sources.safe_xml import clean
from lrcc.domain.errors import SourceError


def parse_json(data: bytes, source: str) -> object:
    """Parse a JSON answer.

    Args:
        data: The response body.
        source: The source's name, for the error.

    Returns:
        The parsed document.

    Raises:
        SourceError: If the body is not JSON, or nests too deeply to read.
    """
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as problem:
        raise SourceError(
            f"{source} answered with JSON that cannot be read", [type(problem).__name__]
        ) from None


def mapping(value: object) -> dict[str, object]:
    """Return ``value`` if it is a JSON object, or an empty one."""
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def items(value: object) -> list[object]:
    """Return ``value`` if it is a JSON array, or an empty one."""
    return value if isinstance(value, list) else []


def text(value: object) -> str:
    """Return ``value`` as clean text if it is a string or a number, or an empty string."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, int | float):
        return str(value)
    return ""
