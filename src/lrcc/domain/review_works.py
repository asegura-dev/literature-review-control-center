"""A review's works, assembled once from what its storage holds, after checking it.

Deduplication and screening need the same picture of a review: every record with its work, the
person's decisions on pairs, the groups those make, and the runs the review counts. A feature may
not import another (ADR-0003), so the picture is assembled here, as pure functions over data the
features have read. Both features therefore refuse the same things: a log that does not verify,
records that do not match their digests, links to works the catalog no longer holds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lrcc.domain.errors import ReviewError
from lrcc.domain.fuzzy import (
    LoggedDecision,
    PairDecision,
    WorkFacts,
    current_decisions,
    decision_chain_problems,
    groups,
    work_facts,
)
from lrcc.domain.record import Record
from lrcc.domain.runs import LoggedRun, chain_problems, counted_runs, records_digest
from lrcc.domain.works import Link, Work


@dataclass(frozen=True)
class ReviewState:
    """What a review's storage holds, read once: runs, records, links and decisions on pairs."""

    review_id: str
    protocol_sha256: str
    strings: dict[str, str]
    log: tuple[LoggedRun, ...]
    records: dict[str, tuple[Record, ...]]
    links: tuple[Link, ...]
    decisions: tuple[LoggedDecision, ...]

    @property
    def counted(self) -> set[str]:
        """The runs the review counts: per source, the latest of its current string (ADR-0019)."""
        return counted_runs(self.log, self.strings)


@dataclass(frozen=True)
class ReviewWorks:
    """Every work of a review, what is shown of it, and the groups a person's decisions make."""

    facts: dict[str, WorkFacts]
    order: list[str]
    identities: dict[str, str]
    current: dict[tuple[str, str], PairDecision]
    group_of: dict[str, str]
    unstable: int

    def members(self) -> dict[str, list[str]]:
        """Return each group's works, by the group's name, in naming order."""
        found: dict[str, list[str]] = {}
        for work_id in self.order:
            found.setdefault(self.group_of[work_id], []).append(work_id)
        return found


def check_state(state: ReviewState) -> None:
    """Refuse a review whose logs or records were edited, before anything is built on them.

    Args:
        state: What the review's storage holds.

    Raises:
        ReviewError: If the run log does not verify, a run's records do not match their digest,
            or the decisions' log does not verify.
    """
    if chain_problems(state.log):
        raise ReviewError(
            f"the run log of {state.review_id!r} does not verify",
            ["run lrcc status to see where; nothing was changed"],
        )
    for logged in state.log:
        run = logged.run
        if records_digest(state.records[run.run_id]) != run.records_sha256:
            raise ReviewError(
                f"the records of {run.run_id} do not match the log",
                ["run lrcc verify; nothing was changed"],
            )
    if decision_chain_problems(state.decisions):
        raise ReviewError(
            f"the decisions log of {state.review_id!r} does not verify",
            ["run lrcc verify to see where; nothing was changed"],
        )


def unlinked(state: ReviewState) -> int:
    """Return how many stored records no link joins to a work yet."""
    linked = {(link.run_id, link.position) for link in state.links}
    return sum(
        (run_id, position) not in linked
        for run_id, records in state.records.items()
        for position in range(1, len(records) + 1)
    )


def require_linked(state: ReviewState) -> None:
    """Refuse to judge works while some records are not linked to one.

    Raises:
        ReviewError: If any record is not linked yet.
    """
    count = unlinked(state)
    if count:
        raise ReviewError(
            f"{count} record(s) of {state.review_id!r} are not linked to works yet",
            [f"run first: lrcc dedupe {state.review_id}"],
        )


def review_works(state: ReviewState, known: Mapping[str, Work]) -> ReviewWorks:
    """Assemble a review's works and groups from its state and the catalog.

    Args:
        state: What the review's storage holds, already checked.
        known: Every work of the catalog, in the order they were named.

    Returns:
        The works the review's links name, with their facts and groups.

    Raises:
        ReviewError: If a link names a work the catalog does not hold.
    """
    facts = work_facts(
        [(link, state.records[link.run_id][link.position - 1]) for link in state.links]
    )
    missing = set(facts) - set(known)
    if missing:
        raise ReviewError(
            f"the catalog does not hold {len(missing)} of the works {state.review_id!r} links to",
            ["it may have been deleted; rebuilding it by replay is not built yet"],
        )
    order = [work_id for work_id in known if work_id in facts]
    identities = {work_id: known[work_id].identity for work_id in order}
    current = current_decisions(state.decisions)
    return ReviewWorks(
        facts=facts,
        order=order,
        identities=identities,
        current=current,
        group_of=groups(order, identities, current),
        unstable=sum(known[work_id].unstable for work_id in order),
    )
