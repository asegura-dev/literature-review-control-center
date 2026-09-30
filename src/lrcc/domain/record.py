"""A record: one hit returned by one source, and the result of one search (ADR-0011).

A record is what a source said, made uniform. It is not yet a work: several records can describe
one publication, and joining them is deduplication's job.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    """One hit from one source, frozen where it entered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    source_id: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    doi: str | None
    abstract: str | None


class SearchResult(BaseModel):
    """What one search returned: the count the source reported, and the records retrieved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    query: str
    reported: int
    records: tuple[Record, ...]
