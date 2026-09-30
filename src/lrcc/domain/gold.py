"""A gold set: works known to be relevant, used to test a search string (ADR-0014).

A gold set lives beside its protocol, in ``reviews/<review_id>/gold.yaml``, written by a person.
Each work is named by a label and found by its identifiers: a DOI, a PMID, an arXiv identifier,
any of them. A work with none can be listed, and is reported as impossible to check rather than
silently skipped.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    ValidationError,
    field_validator,
)

from lrcc.domain.documents import Text, load_mapping
from lrcc.domain.errors import ReviewError, describe_validation

GOLD_FILE = "gold.yaml"

_DOI = re.compile(r"10\.\d{4,9}/\S+")
_PMID = re.compile(r"[1-9][0-9]{0,9}")
#: New-style (``2508.02104``) or old-style (``cs/0112017``) arXiv identifiers, without version.
_ARXIV = re.compile(r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Za-z-]+)?/\d{7}")
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:")


def _doi(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    for prefix in _DOI_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
    if not _DOI.fullmatch(text):
        raise ValueError("must be a DOI such as 10.1109/TMI.2019.2963882")
    return text.lower()


def _pmid(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not _PMID.fullmatch(text):
        raise ValueError("must be a PMID: digits only")
    return text


def _arxiv_is_text(value: object) -> object:
    # YAML reads an unquoted 2508.02104 as a number. Converting it back is unsafe: 2508.02100
    # would come back as 2508.021, a different identifier. So a number is refused, never fixed.
    if isinstance(value, int | float):
        raise ValueError(
            f"write the arXiv identifier in quotes, as '{value}': unquoted, YAML reads it as a"
            " number, which can lose trailing zeros"
        )
    return value


def _arxiv(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().removeprefix("arXiv:").removeprefix("arxiv:")
    text = re.sub(r"v\d+$", "", text)
    if not _ARXIV.fullmatch(text):
        raise ValueError("must be an arXiv identifier such as 2508.02104")
    return text


class GoldWork(BaseModel):
    """One work known to be relevant, and the identifiers that find it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: Text
    # Each identifier is one optional type with its validators on the whole, so a bad value is
    # reported once, not once per branch of a union.
    doi: Annotated[str | None, AfterValidator(_doi)] = None
    pmid: Annotated[str | int | None, AfterValidator(_pmid)] = None
    arxiv: Annotated[str | None, BeforeValidator(_arxiv_is_text), AfterValidator(_arxiv)] = None
    note: Text | None = None

    @property
    def identifiers(self) -> str:
        """The work's identifiers, as one line for a report."""
        parts = [
            f"{kind}:{value}"
            for kind, value in (("doi", self.doi), ("pmid", self.pmid), ("arxiv", self.arxiv))
            if value
        ]
        return ", ".join(parts) or "no identifier"


class GoldSet(BaseModel):
    """A validated gold set, format 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal[1]
    # Emptiness is checked in the validator below, after the works themselves: a length
    # constraint here also fires when the only work is invalid, and reports a false "empty".
    works: tuple[GoldWork, ...]

    @field_validator("works")
    @classmethod
    def _labels_are_unique(cls, works: tuple[GoldWork, ...]) -> tuple[GoldWork, ...]:
        if not works:
            raise ValueError("must list at least one work")
        labels = [work.label for work in works]
        repeated = sorted({label for label in labels if labels.count(label) > 1})
        if repeated:
            raise ValueError(f"labels must be unique; repeated: {', '.join(repeated)}")
        return works


def parse_gold_set(data: bytes, source: str) -> GoldSet:
    """Parse and validate a gold set file's bytes.

    Args:
        data: The file's contents.
        source: Where it came from, named in any error.

    Returns:
        The validated gold set.

    Raises:
        ReviewError: If the file is not UTF-8, not YAML, or not a valid gold set, listing every
            problem found.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as problem:
        raise ReviewError(
            f"{source} is not UTF-8 text", [f"byte {problem.start}: {problem.reason}"]
        ) from None
    mapping = load_mapping(text, source, ReviewError)
    try:
        return GoldSet.model_validate(mapping)
    except ValidationError as error:
        raise ReviewError(f"{source} is not a valid gold set", describe_validation(error)) from None
