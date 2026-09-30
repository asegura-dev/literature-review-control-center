"""Run a review's search string against one source, as a stored run or as a preview.

``run_search`` is what a review uses (ADR-0012): it asks the source for every record, stores
each raw response with its digest, and appends the run to the hash-chained log. ``search_review``
is the preview (ADR-0011): it asks for a few records and stores nothing, and must not be reported
as a run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version

from lrcc.domain.errors import ReviewError
from lrcc.domain.record import SearchResult
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.runs import MAX_RUN_RECORDS, LoggedRun, build_run
from lrcc.domain.workspace import Workspace
from lrcc.ports.source import Source
from lrcc.ports.store import ReviewStore

#: How many records a preview retrieves unless told otherwise.
PREVIEW_RECORDS = 20


@dataclass(frozen=True)
class SearchOutcome:
    """What a preview returned, and the digest of the protocol whose string was run."""

    review_id: str
    protocol_sha256: str
    result: SearchResult

    def as_dict(self) -> dict[str, object]:
        """Return the outcome as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "protocol_sha256": self.protocol_sha256,
            "source": self.result.source,
            "query": self.result.query,
            "reported": self.result.reported,
            "retrieved": len(self.result.records),
            "stored": False,
            "records": [record.model_dump(mode="json") for record in self.result.records],
        }


@dataclass(frozen=True)
class RunOutcome:
    """A stored run, as logged."""

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


def _search(workspace: Workspace, review_id: str, source: Source, limit: int) -> SearchOutcome:
    loaded = load_review_protocol(workspace, review_id)
    entry = loaded.protocol.sources.get(source.name)
    if entry is None:
        raise ReviewError(
            f"the protocol of {review_id!r} has no search string for {source.name}",
            [f"its sources are: {', '.join(sorted(loaded.protocol.sources))}"],
        )
    return SearchOutcome(review_id, loaded.sha256, source.search(entry.query, limit))


def search_review(
    workspace: Workspace, review_id: str, source: Source, limit: int | None = None
) -> SearchOutcome:
    """Preview the search string ``review_id`` holds for ``source``. Nothing is stored.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol names the search string.
        source: The source to ask.
        limit: The most records to retrieve, or None for a preview's few.

    Returns:
        The source's reported count and the records retrieved.

    Raises:
        ReviewError: If the review has no protocol, or the protocol has no string for the source.
        ProtocolError: If the protocol is invalid.
        NetworkError: If a request is refused or fails.
        SourceError: If the source's answer cannot be read.
    """
    return _search(workspace, review_id, source, limit or PREVIEW_RECORDS)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_search(
    workspace: Workspace,
    review_id: str,
    source: Source,
    store: ReviewStore,
    limit: int | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> RunOutcome:
    """Run the search string ``review_id`` holds for ``source``, and store the run.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol names the search string.
        source: The source to ask.
        store: The review's storage.
        limit: The most records to retrieve, or None for every record, up to the run ceiling.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        The run as logged, with its place in the hash chain.

    Raises:
        ReviewError: If the review has no protocol, or the protocol has no string for the source.
        ProtocolError: If the protocol is invalid.
        NetworkError: If a request is refused or fails. Nothing is stored in that case.
        SourceError: If the source's answer cannot be read. Nothing is stored in that case.
        StoreError: If the run cannot be written.
    """
    started = now()
    outcome = _search(workspace, review_id, source, limit or MAX_RUN_RECORDS)
    finished = now()
    count, _ = store.head()
    run = build_run(
        sequence=count + 1,
        started=started,
        finished=finished,
        protocol_sha256=outcome.protocol_sha256,
        result=outcome.result,
        lrcc_version=version("literature-review-control-center"),
    )
    return RunOutcome(review_id, store.save_run(run, outcome.result))
