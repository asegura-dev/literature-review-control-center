"""A review protocol: question, coded criteria, search strings and extraction fields (ADR-0010).

A protocol is a YAML file written by a person before any search. Its identity is the SHA-256 of
its exact bytes: that digest is what a person registers (on OSF, for instance), and anyone can
recompute it with standard tools. Parsing builds frozen models once, where the file enters, and
nothing downstream re-checks them.
"""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator

from lrcc.domain.documents import Text, load_mapping
from lrcc.domain.errors import ProtocolError, describe_validation
from lrcc.domain.identifiers import ReviewId

#: The version of the protocol file's own format.
PROTOCOL_FORMAT = 1

#: The sources a protocol may name. The first two get adapters in v0.4.0, the others in v0.8.0.
SOURCES = ("arxiv", "ieee", "pubmed", "scopus")

_CODE = re.compile(r"(INC|EXC)[1-9][0-9]*")
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")


def _check_code(value: str) -> str:
    if not _CODE.fullmatch(value):
        raise ValueError("must look like INC1 or EXC1")
    return value


def _check_field_name(value: str) -> str:
    if not _FIELD_NAME.fullmatch(value):
        raise ValueError(
            "must be lowercase letters, digits and underscores, starting with a letter"
        )
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Question(_Frozen):
    """The review question and the framework that structures it, such as PCC or PICO."""

    text: Text
    framework: Text
    elements: Annotated[dict[Text, Text], Field(min_length=1)]


class Criterion(_Frozen):
    """One coded eligibility criterion. Every screening decision will cite one."""

    code: Annotated[str, AfterValidator(_check_code)]
    text: Text


class SourceQuery(_Frozen):
    """The search string for one source, in that source's own syntax."""

    query: Text


class ExtractionField(_Frozen):
    """One field that data extraction fills in for each included work."""

    name: Annotated[str, AfterValidator(_check_field_name)]
    description: Text


class Protocol(_Frozen):
    """A validated review protocol, format 1. Every field is required."""

    format: Literal[1]
    review_id: ReviewId
    title: Text
    question: Question
    criteria: Annotated[tuple[Criterion, ...], Field(min_length=1)]
    sources: Annotated[dict[str, SourceQuery], Field(min_length=1)]
    extraction: Annotated[tuple[ExtractionField, ...], Field(min_length=1)]

    @field_validator("criteria")
    @classmethod
    def _criteria_are_usable(cls, criteria: tuple[Criterion, ...]) -> tuple[Criterion, ...]:
        codes = [criterion.code for criterion in criteria]
        repeated = sorted({code for code in codes if codes.count(code) > 1})
        if repeated:
            raise ValueError(f"codes must be unique; repeated: {', '.join(repeated)}")
        if not any(code.startswith("INC") for code in codes):
            raise ValueError("needs at least one inclusion criterion, such as INC1")
        if not any(code.startswith("EXC") for code in codes):
            raise ValueError("needs at least one exclusion criterion, such as EXC1")
        return criteria

    @field_validator("sources")
    @classmethod
    def _sources_are_known(cls, sources: dict[str, SourceQuery]) -> dict[str, SourceQuery]:
        unknown = sorted(set(sources) - set(SOURCES))
        if unknown:
            raise ValueError(
                f"unknown source {', '.join(unknown)}; the known sources are {', '.join(SOURCES)}"
            )
        return sources

    @field_validator("extraction")
    @classmethod
    def _names_are_unique(cls, fields: tuple[ExtractionField, ...]) -> tuple[ExtractionField, ...]:
        names = [field.name for field in fields]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"names must be unique; repeated: {', '.join(repeated)}")
        return fields

    @property
    def inclusion(self) -> tuple[str, ...]:
        """The inclusion codes, in the order written."""
        return tuple(c.code for c in self.criteria if c.code.startswith("INC"))

    @property
    def exclusion(self) -> tuple[str, ...]:
        """The exclusion codes, in the order written."""
        return tuple(c.code for c in self.criteria if c.code.startswith("EXC"))


def protocol_digest(data: bytes) -> str:
    """Return the SHA-256 of a protocol file's exact bytes, as lowercase hex.

    Args:
        data: The file's contents, unmodified. A changed line ending is a changed protocol.

    Returns:
        The digest ``sha256sum`` and ``Get-FileHash`` print for the same file.
    """
    return hashlib.sha256(data).hexdigest()


def parse_protocol(data: bytes, source: str) -> Protocol:
    """Parse and validate a protocol file's bytes.

    Args:
        data: The file's contents. A UTF-8 byte-order mark, which some editors add, is accepted.
        source: Where it came from, named in any error.

    Returns:
        The validated protocol.

    Raises:
        ProtocolError: If the bytes are not UTF-8, not YAML, or not a valid protocol, listing
            every problem found.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as problem:
        raise ProtocolError(
            f"{source} is not UTF-8 text", [f"byte {problem.start}: {problem.reason}"]
        ) from None
    mapping = load_mapping(text, source, ProtocolError)
    try:
        return Protocol.model_validate(mapping)
    except ValidationError as error:
        raise ProtocolError(
            f"{source} is not a valid protocol", describe_validation(error)
        ) from None
