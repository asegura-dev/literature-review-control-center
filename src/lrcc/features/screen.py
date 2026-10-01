"""Screen a review's groups by title and abstract, as a person decides (ADR-0019).

``open_session`` gathers the groups still to screen, in the review's stateless order, with what
a person needs to judge each: title, authors, year, sources, DOI, and the longest abstract among
the group's records. The session records each decision as soon as it is made, in the screening
log, with the digest of the protocol in force and a kept copy of that protocol. With the pilot,
only the first 50 groups of the order and the frontier cases are presented.

``screen_report`` counts what has been decided, overall and in the pilot, by code and by
protocol version. Like deduplication, screening refuses a review whose logs do not verify.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from lrcc.domain.errors import ConfigError, ReviewError
from lrcc.domain.record import Record
from lrcc.domain.review_works import (
    ReviewState,
    ReviewWorks,
    check_state,
    require_linked,
    review_works,
)
from lrcc.domain.reviews import load_frontier, load_review_protocol
from lrcc.domain.runs import timestamp
from lrcc.domain.screening import (
    EXCLUDE,
    INCLUDE,
    PILOT_SIZE,
    UNCERTAIN,
    LoggedScreen,
    ScreenDecision,
    Verdict,
    check_verdict,
    frontier_groups,
    pilot_groups,
    screened,
    screening_chain_problems,
    screening_order,
)
from lrcc.domain.workspace import Workspace
from lrcc.ports.catalog import WorkCatalog
from lrcc.ports.store import ReviewStore

_VERDICT: dict[str, Verdict] = {INCLUDE: INCLUDE, EXCLUDE: EXCLUDE, UNCERTAIN: UNCERTAIN}


@dataclass(frozen=True)
class ScreenItem:
    """One group as a person judges it."""

    group: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    sources: tuple[str, ...]
    doi: str | None
    abstract: str | None
    members: tuple[str, ...]


@dataclass(frozen=True)
class _Review:
    state: ReviewState
    works: ReviewWorks
    protocol: bytes
    exclusion: dict[str, str]
    log: tuple[LoggedScreen, ...]
    order: list[str]
    pilot: list[str]
    missing_frontier: list[str]
    decided: dict[str, ScreenDecision]


@dataclass
class ScreenSession:
    """The groups left to screen, and the means to record a decision on each."""

    review_id: str
    reviewer: str
    pilot: bool
    exclusion: dict[str, str]
    items: list[ScreenItem]
    to_screen: int
    decided: int
    missing_frontier: list[str]
    _store: ReviewStore = field(repr=False)
    _protocol: bytes = field(repr=False)
    _protocol_sha256: str = field(repr=False)
    _groups: dict[str, str] = field(repr=False)
    _scope: set[str] = field(repr=False)
    _now: Callable[[], datetime] = field(repr=False)

    def record(self, work_id: str, verdict: str, code: str | None, note: str) -> ScreenDecision:
        """Record a decision on the group of ``work_id``, at once.

        Args:
            work_id: Any work of the group.
            verdict: ``include``, ``exclude`` or ``uncertain``.
            code: The exclusion code, for an exclusion only.
            note: The person's note, or an empty string.

        Returns:
            The decision, as recorded.

        Raises:
            ReviewError: If the work is not one the review screens, or the decision cannot be
                carried by the protocol. Nothing is recorded.
            StoreError: If the decision cannot be written.
        """
        if self._groups.get(work_id) not in self._scope:
            raise ReviewError(
                f"{work_id!r} is not a work {self.review_id!r} screens",
                ["screened works are those of the counted runs; see lrcc screen-report"],
            )
        check_verdict(verdict, code, self.exclusion)
        self._store.keep_protocol(self._protocol)
        decision = ScreenDecision(
            work_id=work_id,
            decision=_VERDICT[verdict],
            code=code,
            note=note,
            pilot=self.pilot,
            protocol_sha256=self._protocol_sha256,
            reviewer=self.reviewer,
            decided_at=timestamp(self._now()),
        )
        self._store.save_screening(decision)
        return decision


@dataclass(frozen=True)
class Tally:
    """How a set of groups stands: decided by verdict and by code, and pending."""

    groups: int
    include: int
    exclude: int
    uncertain: int
    by_code: dict[str, int]

    @property
    def pending(self) -> int:
        """Groups with no decision yet."""
        return self.groups - self.include - self.exclude - self.uncertain

    def as_dict(self) -> dict[str, object]:
        """Return the tally as JSON-ready data."""
        return {
            "groups": self.groups,
            "include": self.include,
            "exclude": self.exclude,
            "uncertain": self.uncertain,
            "pending": self.pending,
            "excluded_by_code": dict(self.by_code),
        }


@dataclass(frozen=True)
class ScreenReport:
    """Where screening stands, overall and in the pilot, and under which protocols."""

    review_id: str
    order_rule: str
    overall: Tally
    pilot: Tally
    protocol_sha256: str
    versions: dict[str, int]
    reviewers: tuple[str, ...]
    missing_frontier: list[str]

    def as_dict(self) -> dict[str, object]:
        """Return the report as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "order": self.order_rule,
            "overall": self.overall.as_dict(),
            "pilot": self.pilot.as_dict(),
            "protocol_sha256": self.protocol_sha256,
            "decisions_by_protocol": dict(self.versions),
            "reviewers": list(self.reviewers),
            "frontier_not_found": list(self.missing_frontier),
        }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _review(
    workspace: Workspace, review_id: str, store: ReviewStore, catalog: WorkCatalog
) -> _Review:
    loaded = load_review_protocol(workspace, review_id)
    log = store.log()
    state = ReviewState(
        review_id=review_id,
        protocol_sha256=loaded.sha256,
        strings={name: entry.query for name, entry in loaded.protocol.sources.items()},
        log=log,
        records={logged.run.run_id: store.records(logged.run.run_id) for logged in log},
        links=store.links(),
        decisions=store.decisions(),
    )
    check_state(state)
    require_linked(state)
    screening = store.screenings()
    if screening_chain_problems(screening):
        raise ReviewError(
            f"the screening log of {review_id!r} does not verify",
            ["run lrcc verify to see where; nothing was changed"],
        )
    works = review_works(state, catalog.works())
    counted = state.counted
    scope = {works.group_of[link.work_id] for link in state.links if link.run_id in counted}
    order = screening_order(review_id, scope)
    frontier = load_frontier(workspace, review_id)
    found, missing = (
        frontier_groups(frontier, catalog.identifiers(), works.group_of) if frontier else ({}, [])
    )
    in_scope = [group for group in found.values() if group in scope]
    return _Review(
        state=state,
        works=works,
        protocol=loaded.path.read_bytes(),
        exclusion={c.code: c.text for c in loaded.protocol.criteria if c.code.startswith("EXC")},
        log=screening,
        order=order,
        pilot=pilot_groups(order, in_scope),
        missing_frontier=missing,
        decided=screened(screening, works.group_of),
    )


def _item(group: str, members: tuple[str, ...], records: dict[str, list[Record]]) -> ScreenItem:
    own = [record for work_id in members for record in records[work_id]]
    first = records[group][0]
    abstracts = [record.abstract for record in own if record.abstract]
    return ScreenItem(
        group=group,
        title=first.title,
        authors=first.authors,
        year=first.year,
        sources=tuple(sorted({record.source for record in own})),
        doi=next((record.doi for record in own if record.doi), None),
        abstract=max(abstracts, key=len) if abstracts else None,
        members=members,
    )


def open_session(
    workspace: Workspace,
    review_id: str,
    store: ReviewStore,
    catalog: WorkCatalog,
    reviewer: str | None,
    pilot: bool = False,
    now: Callable[[], datetime] = _utc_now,
) -> ScreenSession:
    """Gather the groups left to screen, in order, and open a session to record decisions.

    Args:
        workspace: The accepted workspace.
        review_id: The review to screen.
        store: The review's storage.
        catalog: The workspace's work catalog.
        reviewer: The person screening, from the configuration.
        pilot: Whether to present only the pilot's groups, and mark decisions as the pilot's.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        The session: the undecided groups, in screening order, and how far screening has gone.

    Raises:
        ConfigError: If no reviewer is configured.
        ReviewError: If a log does not verify, a record is not linked yet, or the frontier file is
            not valid.
        ProtocolError: If the protocol is invalid.
        StoreError: If the review's storage or the catalog cannot be read.
    """
    if not reviewer:
        raise ConfigError(
            "recording a decision needs the reviewer's name",
            ["add a line reviewer: Your Name to the configuration file"],
        )
    review = _review(workspace, review_id, store, catalog)
    targets = review.pilot if pilot else review.order
    records: dict[str, list[Record]] = {}
    for link in review.state.links:
        records.setdefault(link.work_id, []).append(
            review.state.records[link.run_id][link.position - 1]
        )
    members = review.works.members()
    return ScreenSession(
        review_id=review_id,
        reviewer=reviewer,
        pilot=pilot,
        exclusion=review.exclusion,
        items=[
            _item(group, tuple(members[group]), records)
            for group in targets
            if group not in review.decided
        ],
        to_screen=len(targets),
        decided=sum(group in review.decided for group in targets),
        missing_frontier=review.missing_frontier,
        _store=store,
        _protocol=review.protocol,
        _protocol_sha256=review.state.protocol_sha256,
        _groups=review.works.group_of,
        _scope=set(review.order),
        _now=now,
    )


def _tally(groups: list[str], decided: dict[str, ScreenDecision]) -> Tally:
    verdicts = Counter(decided[group].decision for group in groups if group in decided)
    codes = Counter(
        decided[group].code or ""
        for group in groups
        if group in decided and decided[group].decision == EXCLUDE
    )
    return Tally(
        groups=len(groups),
        include=verdicts[INCLUDE],
        exclude=verdicts[EXCLUDE],
        uncertain=verdicts[UNCERTAIN],
        by_code=dict(sorted(codes.items())),
    )


def screen_report(
    workspace: Workspace, review_id: str, store: ReviewStore, catalog: WorkCatalog
) -> ScreenReport:
    """Count where screening stands, overall and in the pilot, by code and by protocol.

    Args:
        workspace: The accepted workspace.
        review_id: The review to report on.
        store: The review's storage.
        catalog: The workspace's work catalog.

    Returns:
        The tallies, the decisions per protocol digest, the reviewers, and the frontier cases
        the searches did not find.

    Raises:
        ReviewError: If a log does not verify or a record is not linked yet.
        ProtocolError: If the protocol is invalid.
        StoreError: If the review's storage or the catalog cannot be read.
    """
    review = _review(workspace, review_id, store, catalog)
    in_force = [review.decided[group] for group in review.order if group in review.decided]
    return ScreenReport(
        review_id=review_id,
        order_rule=f"by the SHA-256 of '{review_id}|work_id', in hexadecimal; the pilot is the"
        f" first {PILOT_SIZE}, plus the frontier cases",
        overall=_tally(review.order, review.decided),
        pilot=_tally(review.pilot, review.decided),
        protocol_sha256=review.state.protocol_sha256,
        versions=dict(Counter(decision.protocol_sha256 for decision in in_force)),
        reviewers=tuple(sorted({decision.reviewer for decision in in_force})),
        missing_frontier=review.missing_frontier,
    )
