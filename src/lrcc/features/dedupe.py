"""Deduplicate a review's records into works, through shared identifiers (ADR-0017).

``dedupe_review`` takes every record not yet linked, in the order the run log recorded them. It
joins each record to the work that already holds one of its identifiers, or creates a work, and
stores the links with their reasons. The catalog is written first and the review's links
second, so a failure in between leaves only identifiers that the next pass finds again.

It refuses a review whose run log does not verify or whose records were edited: works built on
altered records would prove nothing. Fuzzy matching on titles, which a person confirms, is not
here yet.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from lrcc.domain.errors import ReviewError
from lrcc.domain.record import Record
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.runs import chain_problems, records_digest, timestamp
from lrcc.domain.works import NEW, link_records
from lrcc.domain.workspace import Workspace
from lrcc.ports.catalog import WorkCatalog
from lrcc.ports.store import ReviewStore


@dataclass(frozen=True)
class RunCount:
    """One run's records: how many first named a work, and whether it used the current protocol."""

    run_id: str
    source: str
    records: int
    first_seen: int
    current_protocol: bool

    @property
    def already_seen(self) -> int:
        """The run's records that joined a work an earlier record had named."""
        return self.records - self.first_seen


@dataclass(frozen=True)
class DedupeResult:
    """What a pass linked, and where the review's works stand."""

    review_id: str
    linked_now: int
    joined_by: dict[str, int]
    runs: tuple[RunCount, ...]
    current_records: int
    current_works: int
    works: int
    unstable: int

    @property
    def current_duplicates(self) -> int:
        """Records of the current protocol's runs that are another record of the same work."""
        return self.current_records - self.current_works

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "linked_now": self.linked_now,
            "joined_by": dict(sorted(self.joined_by.items())),
            "works": self.works,
            "unstable": self.unstable,
            "current_protocol": {
                "records": self.current_records,
                "works": self.current_works,
                "duplicates": self.current_duplicates,
            },
            "runs": [
                {
                    "run_id": run.run_id,
                    "source": run.source,
                    "records": run.records,
                    "first_seen": run.first_seen,
                    "already_seen": run.already_seen,
                    "current_protocol": run.current_protocol,
                }
                for run in self.runs
            ],
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def dedupe_review(
    workspace: Workspace,
    review_id: str,
    store: ReviewStore,
    catalog: WorkCatalog,
    now: Callable[[], datetime] = _utc_now,
) -> DedupeResult:
    """Link every record of ``review_id`` not yet linked to its work.

    Args:
        workspace: The accepted workspace.
        review_id: The review to deduplicate.
        store: The review's storage.
        catalog: The workspace's work catalog.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        What this pass linked, and the review's works, overall and under the current protocol.

    Raises:
        ReviewError: If the review has no protocol, its run log does not verify, its records do
            not match their digests, or its links name works the catalog does not hold.
        ProtocolError: If the protocol is invalid.
        DedupeError: If a record carries identifiers of two works, or a new work's name is
            taken. Nothing is written in that case.
        StoreError: If the catalog or the review's database cannot be read or written.
    """
    loaded = load_review_protocol(workspace, review_id)
    log = store.log()
    if chain_problems(log):
        raise ReviewError(
            f"the run log of {review_id!r} does not verify",
            ["run lrcc status to see where; nothing was deduplicated"],
        )
    linked = {(link.run_id, link.position) for link in store.links()}
    items: list[tuple[str, int, Record]] = []
    for logged in log:
        run = logged.run
        records = store.records(run.run_id)
        if records_digest(records) != run.records_sha256:
            raise ReviewError(
                f"the records of {run.run_id} do not match the log",
                ["run lrcc verify; nothing was deduplicated"],
            )
        items.extend(
            (run.run_id, position, record)
            for position, record in enumerate(records, start=1)
            if (run.run_id, position) not in linked
        )
    result = link_records(items, catalog.identifiers())
    catalog.add(result.works, result.aliases, timestamp(now()))
    store.save_links(result.links)

    links = store.links()
    works = catalog.works()
    review_works = {link.work_id for link in links}
    missing = review_works - set(works)
    if missing:
        raise ReviewError(
            f"the catalog does not hold {len(missing)} of the works {review_id!r} links to",
            ["it may have been deleted; rebuilding it by replay is not built yet"],
        )
    current = {logged.run.run_id for logged in log if logged.run.protocol_sha256 == loaded.sha256}
    current_links = [link for link in links if link.run_id in current]
    return DedupeResult(
        review_id=review_id,
        linked_now=len(result.links),
        joined_by=dict(
            Counter(
                link.matched_by.split(":", 1)[0] for link in result.links if link.matched_by != NEW
            )
        ),
        runs=tuple(
            RunCount(
                run_id=logged.run.run_id,
                source=logged.run.source,
                records=sum(link.run_id == logged.run.run_id for link in links),
                first_seen=sum(
                    link.run_id == logged.run.run_id and link.matched_by == NEW for link in links
                ),
                current_protocol=logged.run.run_id in current,
            )
            for logged in log
        ),
        current_records=len(current_links),
        current_works=len({link.work_id for link in current_links}),
        works=len(review_works),
        unstable=sum(works[work_id].unstable for work_id in review_works),
    )
