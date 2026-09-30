"""A run: one stored execution of one search string, and the hash chain of the run log (ADR-0012).

A run records what was asked, when, what the source reported, and the digest of every raw
response it stored. Runs are appended, never edited. Each entry's hash covers the entry and the
hash before it, so an edit, a removal or a reordering breaks every hash that follows.

A run is either a search LRCC made through a source's API, or an import of the files a person
exported from the database's own interface (ADR-0016). The second records the day of the search.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from lrcc.domain.record import Record, SearchResult

#: What the first entry of a chain names as the hash before it.
GENESIS = "0" * 64

#: A run retrieves every record a source reports, up to this many (ADR-0012).
MAX_RUN_RECORDS = 10_000


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 of ``data`` as lowercase hex.

    Args:
        data: The bytes to hash.

    Returns:
        The digest, as ``sha256sum`` prints it.
    """
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class StoredResponse(BaseModel):
    """One raw response as the log knows it: its file, what was asked, its size and digest.

    For an imported run, ``url`` holds the name of the file the person gave, since nothing was
    asked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str
    url: str
    size: int
    sha256: str


class Imported(BaseModel):
    """What an imported run records besides a search's fields (ADR-0016)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal["ris"]
    #: The day the person ran the search in the database's interface, as YYYY-MM-DD.
    searched_on: str


class Run(BaseModel):
    """One stored execution of one search string against one source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: str
    finished_at: str
    source: str
    query: str
    query_sha256: str
    protocol_sha256: str
    reported: int
    retrieved: int
    lrcc_version: str
    responses: tuple[StoredResponse, ...]
    records_sha256: str
    imported: Imported | None = None

    @property
    def complete(self) -> bool:
        """Whether every record the source reported was retrieved."""
        return self.retrieved >= self.reported

    @property
    def searched_on(self) -> str:
        """The day the search ran: the day given for an import, else the UTC day it started."""
        return self.imported.searched_on if self.imported else self.started_at[:10]

    def entry(self) -> str:
        """Return the run as the canonical JSON document the log stores and hashes.

        A field added after v0.7.0 is optional, and left out while empty. An entry written
        before the field existed keeps its canonical form, and so its hash (ADR-0016).
        """
        return _canonical(self.model_dump(mode="json", exclude_none=True))


class LoggedRun(BaseModel):
    """A run as read back from the log, with its place in the chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run: Run
    entry: str
    prev_hash: str
    entry_hash: str


def timestamp(moment: datetime) -> str:
    """Format a UTC moment the way runs record it.

    Args:
        moment: A timezone-aware moment.

    Returns:
        The moment in UTC, to the second, such as ``2026-09-30T14:15:00Z``.
    """
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id_for(sequence: int, started: datetime, source: str) -> str:
    """Name a run by its place in the review, its start time and its source.

    Args:
        sequence: The run's number in the review, from 1.
        started: When the run started, in UTC.
        source: The source's name.

    Returns:
        An identifier such as ``0001-20260930T141500Z-pubmed``: unique, and sorted in order.
    """
    return f"{sequence:04d}-{started.strftime('%Y%m%dT%H%M%SZ')}-{source}"


def response_file(position: int) -> str:
    """Name the file of the ``position``-th raw response of a run, from 1.

    Args:
        position: The response's place in the run.

    Returns:
        A file name such as ``response-0001.raw``.
    """
    return f"response-{position:04d}.raw"


def records_digest(records: Sequence[Record]) -> str:
    """Return the digest of a run's records, in the order the source gave them.

    Args:
        records: The records derived from the run's responses.

    Returns:
        The SHA-256 of their canonical JSON. A replay that derives the same records gets the same
        digest.
    """
    return sha256_hex(_canonical([record.model_dump(mode="json") for record in records]).encode())


def build_run(
    *,
    sequence: int,
    started: datetime,
    finished: datetime,
    protocol_sha256: str,
    result: SearchResult,
    lrcc_version: str,
    imported: Imported | None = None,
) -> Run:
    """Describe a finished search as a run.

    Args:
        sequence: The run's number in the review, from 1.
        started: When the search started, in UTC. For an import, when the import started.
        finished: When it finished, in UTC.
        protocol_sha256: The digest of the protocol the search string came from.
        result: What the source returned, with its raw responses.
        lrcc_version: The version of LRCC that ran the search.
        imported: For an import, its format and the day of the search; None for an API search.

    Returns:
        The run, with the digest and size of every response and the digest of the records.
    """
    responses = tuple(
        StoredResponse(
            file=response_file(position),
            url=response.url,
            size=len(response.body),
            sha256=sha256_hex(response.body),
        )
        for position, response in enumerate(result.responses, start=1)
    )
    return Run(
        run_id=run_id_for(sequence, started, result.source),
        started_at=timestamp(started),
        finished_at=timestamp(finished),
        source=result.source,
        query=result.query,
        query_sha256=sha256_hex(result.query.encode()),
        protocol_sha256=protocol_sha256,
        reported=result.reported,
        retrieved=len(result.records),
        lrcc_version=lrcc_version,
        responses=responses,
        records_sha256=records_digest(result.records),
        imported=imported,
    )


def entry_hash(prev_hash: str, entry: str) -> str:
    """Return the hash of a log entry: the hash before it, a newline, then the entry.

    Args:
        prev_hash: The hash of the previous entry, or :data:`GENESIS` for the first.
        entry: The entry's canonical JSON.

    Returns:
        The entry's hash.
    """
    return sha256_hex(f"{prev_hash}\n{entry}".encode())


def chain_problems(log: Sequence[LoggedRun]) -> list[str]:
    """Recompute the chain and return what does not hold, one line per problem.

    Args:
        log: The log's entries, in order.

    Returns:
        Nothing if the chain is intact. Otherwise each entry whose stored hash, link to the entry
        before it, or content does not match.
    """
    problems = []
    expected_prev = GENESIS
    for logged in log:
        name = logged.run.run_id
        if logged.prev_hash != expected_prev:
            problems.append(f"{name}: does not follow the entry before it")
        if entry_hash(logged.prev_hash, logged.entry) != logged.entry_hash:
            problems.append(f"{name}: its content does not match its hash")
        if logged.run.entry() != logged.entry:
            problems.append(f"{name}: its entry is not in canonical form")
        expected_prev = logged.entry_hash
    return problems
