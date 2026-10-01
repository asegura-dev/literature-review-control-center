"""Store a database's RIS export of the protocol's string as a run (ADR-0016).

Some searches cannot go through an API: the key awaits approval, or the institution grants the
full records only through the database's own interface. A person then runs the protocol's string
there and exports the results as RIS. ``import_run`` stores the files as a run: each one byte for
byte, as an API answer would be, in the same hash-chained log, so ``status``, ``verify`` and
``replay`` treat the run like any other.

LRCC does not run such a search itself, so the run records what the person states: the day of
the search and the count the database reported. A file already stored in the review is refused,
because its records would be counted twice.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

from lrcc.domain.errors import ReviewError, SourceError
from lrcc.domain.record import RawResponse, SearchResult
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.ris import read_ris
from lrcc.domain.runs import Imported, LoggedRun, build_run, sha256_hex
from lrcc.domain.workspace import Workspace
from lrcc.ports.store import ReviewStore

#: The largest file accepted, the ceiling the HTTP client puts on one answer. An export of one
#: search is far smaller.
MAX_EXPORT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class ImportOutcome:
    """An imported run, as logged."""

    review_id: str
    logged: LoggedRun

    def as_dict(self) -> dict[str, object]:
        """Return the outcome as JSON-ready data."""
        run = self.logged.run
        return {
            "review_id": self.review_id,
            "stored": True,
            "complete": run.complete,
            "entry_hash": self.logged.entry_hash,
            **run.model_dump(mode="json"),
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def import_run(
    workspace: Workspace,
    review_id: str,
    source: str,
    files: Sequence[Path],
    searched_on: date,
    reported: int,
    store: ReviewStore,
    now: Callable[[], datetime] = _utc_now,
) -> ImportOutcome:
    """Store the RIS files a database exported for the protocol's string, as one run.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol names the search string.
        source: The source the files were exported from, one the protocol names.
        files: The exported files of one search, in the order they were exported.
        searched_on: The day the search was run in the database's interface.
        reported: The count the database reported for the search.
        store: The review's storage.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        The run as logged, with its place in the hash chain.

    Raises:
        ReviewError: If the protocol has no string for the source, no file is given, the day is
            in the future, or a file is given twice or is already stored. Nothing is stored.
        ProtocolError: If the protocol is invalid.
        SourceError: If a file cannot be read, is too large, or is not RIS. Nothing is stored.
        StoreError: If the run cannot be written.
    """
    started = now()
    loaded = load_review_protocol(workspace, review_id)
    entry = loaded.protocol.sources.get(source)
    if entry is None:
        raise ReviewError(
            f"the protocol of {review_id!r} has no search string for {source}",
            [f"its sources are: {', '.join(sorted(loaded.protocol.sources))}"],
        )
    if not files:
        raise ReviewError("no exported file was given", ["name the RIS file(s) of the search"])
    # A day of tolerance: in the time zones ahead of UTC, today is already tomorrow.
    if searched_on > started.date() + timedelta(days=1):
        raise ReviewError(
            f"the day of the search, {searched_on.isoformat()}, is in the future",
            ["give the day the search was run in the database, as YYYY-MM-DD"],
        )
    bodies = [_read(path) for path in files]
    _refuse_repeats(files, bodies, store)
    records = tuple(
        record
        for path, body in zip(files, bodies, strict=True)
        for record in read_ris(body, source, path.name)
    )
    result = SearchResult(
        source=source,
        query=entry.query,
        reported=reported,
        records=records,
        responses=tuple(
            RawResponse(url=path.name, body=body) for path, body in zip(files, bodies, strict=True)
        ),
    )
    count, _ = store.head()
    run = build_run(
        sequence=count + 1,
        started=started,
        finished=now(),
        protocol_sha256=loaded.sha256,
        result=result,
        lrcc_version=version("literature-review-control-center"),
        imported=Imported(format="ris", searched_on=searched_on.isoformat()),
    )
    return ImportOutcome(review_id, store.save_run(run, result))


def _read(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_EXPORT_BYTES:
            raise SourceError(
                f"{path.name} is larger than {MAX_EXPORT_BYTES // 2**20} MB",
                ["the export of one search is far smaller; check that this is the right file"],
            )
        return path.read_bytes()
    except OSError as problem:
        raise SourceError(
            f"cannot read {path}", [problem.strerror or type(problem).__name__]
        ) from None


def _refuse_repeats(files: Sequence[Path], bodies: Sequence[bytes], store: ReviewStore) -> None:
    digests = [sha256_hex(body) for body in bodies]
    for position, digest in enumerate(digests):
        if digest in digests[:position]:
            raise ReviewError(
                f"{files[position].name} holds the same bytes as a file given before it",
                ["give each exported file once"],
            )
    stored = {
        response.sha256: logged.run.run_id
        for logged in store.log()
        for response in logged.run.responses
    }
    for path, digest in zip(files, digests, strict=True):
        if digest in stored:
            raise ReviewError(
                f"{path.name} is already stored, in run {stored[digest]}",
                ["importing it again would count its records twice"],
            )
