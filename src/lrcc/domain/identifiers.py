"""Identifiers that become folder names, validated before they touch a path (ADR-0006).

A ``review_id`` names the folder ``reviews/<review_id>/``. It is chosen by a person, and is never
derived from a title.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

from lrcc.domain.errors import ReviewError

REVIEW_ID_MAX_LENGTH = 40
REVIEW_ID_RULE = (
    f"must be 1 to {REVIEW_ID_MAX_LENGTH} lowercase letters, digits and single hyphens,"
    " like 'example-review'"
)
_REVIEW_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def review_id_problem(value: str) -> str | None:
    """Return what is wrong with ``value`` as a review id, or None if it is valid.

    Args:
        value: A candidate review id.

    Returns:
        The rule it breaks, or None.
    """
    if len(value) > REVIEW_ID_MAX_LENGTH or not _REVIEW_ID.fullmatch(value):
        return REVIEW_ID_RULE
    return None


def require_review_id(value: str) -> str:
    """Return ``value`` if it is a valid review id.

    Args:
        value: A candidate review id, typically typed by a person.

    Returns:
        The same value.

    Raises:
        ReviewError: If it is not a valid review id.
    """
    problem = review_id_problem(value)
    if problem is not None:
        raise ReviewError(f"{value!r} is not a valid review id", [problem])
    return value


def _check_review_id(value: str) -> str:
    problem = review_id_problem(value)
    if problem is not None:
        raise ValueError(problem)
    return value


#: A review id inside a validated model.
ReviewId = Annotated[str, AfterValidator(_check_review_id)]
