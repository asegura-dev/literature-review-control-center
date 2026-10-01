"""Deduplicate a review's records into works: exactly, then with a person (ADR-0017, ADR-0018).

One capability, three steps:

- ``dedupe_review`` takes every record not yet linked, in log order, and joins it to the work
  that already holds one of its identifiers, or creates a work. The catalog is written first and
  the review's links second, so a failure in between leaves only identifiers that the next pass
  finds again.
- ``list_candidates`` proposes pairs of works whose titles score at or above a threshold, for a
  person to judge, and can write them to a new CSV file.
- ``decide_pairs`` reads that file back and appends each decision to a hash-chained log. Works
  joined by ``same`` form a group, the unit the review counts.

Every step refuses a review whose logs do not verify or whose records were edited: works built
on altered records, or on altered decisions, would prove nothing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from lrcc.domain.errors import ConfigError, ReviewError
from lrcc.domain.fuzzy import (
    CANDIDATE_MIN,
    SAME,
    Candidate,
    LoggedDecision,
    PairDecision,
    WorkFacts,
    candidate_pairs,
    contradictions,
    current_decisions,
    decision_chain_problems,
    groups,
    pair_of,
    pair_score,
    work_facts,
)
from lrcc.domain.pairs_csv import read_pairs, write_pairs
from lrcc.domain.record import Record
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.runs import LoggedRun, chain_problems, records_digest, timestamp
from lrcc.domain.works import NEW, Link, link_records
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
    """What a pass linked, and where the review's works and groups stand."""

    review_id: str
    linked_now: int
    joined_by: dict[str, int]
    runs: tuple[RunCount, ...]
    current_records: int
    current_works: int
    current_groups: int
    works: int
    groups: int
    unstable: int
    decisions: int

    @property
    def by_identifiers(self) -> int:
        """Duplicates of the current protocol's runs removed by a shared identifier."""
        return self.current_records - self.current_works

    @property
    def by_person(self) -> int:
        """Duplicates of the current protocol's runs removed by a person's ``same``."""
        return self.current_works - self.current_groups

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "linked_now": self.linked_now,
            "joined_by": dict(sorted(self.joined_by.items())),
            "works": self.works,
            "groups": self.groups,
            "unstable": self.unstable,
            "decisions": self.decisions,
            "current_protocol": {
                "records": self.current_records,
                "works": self.current_works,
                "groups": self.current_groups,
                "duplicates": self.current_records - self.current_groups,
                "by_identifiers": self.by_identifiers,
                "by_person": self.by_person,
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


@dataclass(frozen=True)
class CandidatesResult:
    """The pairs proposed to a person, with what is shown of each work."""

    review_id: str
    minimum: float
    pairs: tuple[Candidate, ...]
    facts: dict[str, WorkFacts]
    written: str | None

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "minimum": self.minimum,
            "written": self.written,
            "pairs": [
                {
                    "work_a": pair.work_a,
                    "work_b": pair.work_b,
                    "score": pair.score,
                    **{
                        f"{field}_{side}": getattr(self.facts[work_id], field)
                        for side, work_id in (("a", pair.work_a), ("b", pair.work_b))
                        for field in ("title", "first_author", "year", "sources", "doi")
                    },
                }
                for pair in self.pairs
            ],
        }


@dataclass(frozen=True)
class DecideResult:
    """What reading a decisions file recorded."""

    review_id: str
    reviewer: str
    same: int
    different: int
    unchanged: int
    pending: int
    groups: int

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "reviewer": self.reviewer,
            "recorded": {"same": self.same, "different": self.different},
            "unchanged": self.unchanged,
            "pending": self.pending,
            "groups": self.groups,
        }


@dataclass(frozen=True)
class _State:
    protocol_sha256: str
    log: tuple[LoggedRun, ...]
    records: dict[str, tuple[Record, ...]]
    links: tuple[Link, ...]
    decisions: tuple[LoggedDecision, ...]


@dataclass(frozen=True)
class _Works:
    facts: dict[str, WorkFacts]
    order: list[str]
    identities: dict[str, str]
    current: dict[tuple[str, str], PairDecision]
    group_of: dict[str, str]
    unstable: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _load(workspace: Workspace, review_id: str, store: ReviewStore) -> _State:
    loaded = load_review_protocol(workspace, review_id)
    log = store.log()
    if chain_problems(log):
        raise ReviewError(
            f"the run log of {review_id!r} does not verify",
            ["run lrcc status to see where; nothing was changed"],
        )
    records = {}
    for logged in log:
        run = logged.run
        records[run.run_id] = store.records(run.run_id)
        if records_digest(records[run.run_id]) != run.records_sha256:
            raise ReviewError(
                f"the records of {run.run_id} do not match the log",
                ["run lrcc verify; nothing was changed"],
            )
    decisions = store.decisions()
    if decision_chain_problems(decisions):
        raise ReviewError(
            f"the decisions log of {review_id!r} does not verify",
            ["run lrcc verify to see where; nothing was changed"],
        )
    return _State(loaded.sha256, log, records, store.links(), decisions)


def _works(review_id: str, state: _State, catalog: WorkCatalog) -> _Works:
    facts = work_facts(
        [(link, state.records[link.run_id][link.position - 1]) for link in state.links]
    )
    known = catalog.works()
    missing = set(facts) - set(known)
    if missing:
        raise ReviewError(
            f"the catalog does not hold {len(missing)} of the works {review_id!r} links to",
            ["it may have been deleted; rebuilding it by replay is not built yet"],
        )
    order = [work_id for work_id in known if work_id in facts]
    identities = {work_id: known[work_id].identity for work_id in order}
    current = current_decisions(state.decisions)
    return _Works(
        facts=facts,
        order=order,
        identities=identities,
        current=current,
        group_of=groups(order, identities, current),
        unstable=sum(known[work_id].unstable for work_id in order),
    )


def _require_linked(review_id: str, state: _State) -> None:
    linked = {(link.run_id, link.position) for link in state.links}
    unlinked = sum(
        (run_id, position) not in linked
        for run_id, records in state.records.items()
        for position in range(1, len(records) + 1)
    )
    if unlinked:
        raise ReviewError(
            f"{unlinked} record(s) of {review_id!r} are not linked to works yet",
            [f"run first: lrcc dedupe {review_id}"],
        )


def dedupe_review(
    workspace: Workspace,
    review_id: str,
    store: ReviewStore,
    catalog: WorkCatalog,
    now: Callable[[], datetime] = _utc_now,
) -> DedupeResult:
    """Link every record of ``review_id`` not yet linked to its work, and report the groups.

    Args:
        workspace: The accepted workspace.
        review_id: The review to deduplicate.
        store: The review's storage.
        catalog: The workspace's work catalog.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        What this pass linked, and the review's works and groups, overall and under the current
        protocol. Candidate pairs are not computed here: comparing every pair of titles is the
        slow step, and only ``list_candidates`` pays for it.

    Raises:
        ReviewError: If the review has no protocol, a log does not verify, its records do not
            match their digests, or its links name works the catalog does not hold.
        ProtocolError: If the protocol is invalid.
        DedupeError: If a record carries identifiers of two works, or a new work's name is
            taken. Nothing is written in that case.
        StoreError: If the catalog or the review's database cannot be read or written.
    """
    state = _load(workspace, review_id, store)
    linked = {(link.run_id, link.position) for link in state.links}
    items = [
        (logged.run.run_id, position, record)
        for logged in state.log
        for position, record in enumerate(state.records[logged.run.run_id], start=1)
        if (logged.run.run_id, position) not in linked
    ]
    result = link_records(items, catalog.identifiers())
    catalog.add(result.works, result.aliases, timestamp(now()))
    store.save_links(result.links)

    state = replace(state, links=store.links())
    works = _works(review_id, state, catalog)
    current = {
        logged.run.run_id
        for logged in state.log
        if logged.run.protocol_sha256 == state.protocol_sha256
    }
    current_works = {link.work_id for link in state.links if link.run_id in current}
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
                records=sum(link.run_id == logged.run.run_id for link in state.links),
                first_seen=sum(
                    link.run_id == logged.run.run_id and link.matched_by == NEW
                    for link in state.links
                ),
                current_protocol=logged.run.run_id in current,
            )
            for logged in state.log
        ),
        current_records=sum(link.run_id in current for link in state.links),
        current_works=len(current_works),
        current_groups=len({works.group_of[work_id] for work_id in current_works}),
        works=len(works.facts),
        groups=len(set(works.group_of.values())),
        unstable=works.unstable,
        decisions=len(state.decisions),
    )


def list_candidates(
    workspace: Workspace,
    review_id: str,
    store: ReviewStore,
    catalog: WorkCatalog,
    minimum: float = CANDIDATE_MIN,
    csv_path: Path | None = None,
) -> CandidatesResult:
    """Propose the pairs of works a person should judge, and write them to a new CSV file.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose works to compare.
        store: The review's storage.
        catalog: The workspace's work catalog.
        minimum: The lowest title score proposed.
        csv_path: A file to write the pairs to, which must not exist; or None.

    Returns:
        The pairs, highest score first, with what is shown of each work.

    Raises:
        ReviewError: If a log does not verify, a record is not linked yet, or the file exists or
            cannot be written.
        ProtocolError: If the protocol is invalid.
        StoreError: If the catalog or the review's database cannot be read.
    """
    state = _load(workspace, review_id, store)
    _require_linked(review_id, state)
    works = _works(review_id, state, catalog)
    pairs = candidate_pairs(works.facts, works.group_of, set(works.current), minimum)
    if csv_path is not None:
        try:
            with csv_path.open("xb") as handle:
                handle.write(write_pairs(pairs, works.facts))
        except FileExistsError:
            raise ReviewError(
                f"{csv_path} already exists", ["LRCC never overwrites a file; name a new one"]
            ) from None
        except OSError as problem:
            raise ReviewError(
                f"cannot write {csv_path}", [problem.strerror or type(problem).__name__]
            ) from None
    return CandidatesResult(
        review_id=review_id,
        minimum=minimum,
        pairs=tuple(pairs),
        facts=works.facts,
        written=str(csv_path) if csv_path is not None else None,
    )


def decide_pairs(
    workspace: Workspace,
    review_id: str,
    store: ReviewStore,
    catalog: WorkCatalog,
    path: Path,
    reviewer: str | None,
    now: Callable[[], datetime] = _utc_now,
) -> DecideResult:
    """Record the decisions a person wrote in a candidate-pairs file.

    Args:
        workspace: The accepted workspace.
        review_id: The review the pairs belong to.
        store: The review's storage.
        catalog: The workspace's work catalog.
        path: The file, as the spreadsheet saved it.
        reviewer: The person deciding, from the configuration.
        now: Returns the current moment in UTC. Replaced in tests.

    Returns:
        How many decisions were recorded, unchanged or left pending, and the groups after them.

    Raises:
        ConfigError: If no reviewer is configured. Nothing is recorded.
        ReviewError: If a log does not verify, a record is not linked yet, or the file cannot be
            read, holds an unknown decision or work, a pair twice with two decisions, or a
            contradiction. Nothing is recorded.
        ProtocolError: If the protocol is invalid.
        StoreError: If the review's database cannot be written.
    """
    if not reviewer:
        raise ConfigError(
            "recording a decision needs the reviewer's name",
            ["add a line reviewer: Your Name to the configuration file"],
        )
    state = _load(workspace, review_id, store)
    _require_linked(review_id, state)
    works = _works(review_id, state, catalog)
    try:
        data = path.read_bytes()
    except OSError as problem:
        raise ReviewError(
            f"cannot read {path}", [problem.strerror or type(problem).__name__]
        ) from None
    stamp = timestamp(now())
    current = dict(works.current)
    in_file: dict[tuple[str, str], str] = {}
    new: list[PairDecision] = []
    pending = unchanged = 0
    for row in read_pairs(data, path.name):
        if row.decision is None:
            pending += 1
            continue
        where = f"line {row.line} of {path.name}"
        for work_id in (row.work_a, row.work_b):
            if work_id not in works.facts:
                raise ReviewError(
                    f"{where}: {work_id!r} is not a work of {review_id!r}",
                    ["nothing was recorded"],
                )
        if row.work_a == row.work_b:
            raise ReviewError(f"{where}: a work is paired with itself", ["nothing was recorded"])
        key = pair_of(row.work_a, row.work_b)
        if in_file.setdefault(key, row.decision) != row.decision:
            raise ReviewError(
                f"{where}: the pair appears earlier in the file with another decision",
                ["nothing was recorded"],
            )
        if key in current and current[key].decision == row.decision:
            unchanged += 1
            continue
        decision = PairDecision(
            work_a=key[0],
            work_b=key[1],
            decision=row.decision,
            score=pair_score(works.facts, key[0], key[1]),
            note=row.note,
            reviewer=reviewer,
            decided_at=stamp,
        )
        current[key] = decision
        new.append(decision)
    group_of = groups(works.order, works.identities, current)
    problems = contradictions(group_of, current)
    if problems:
        raise ReviewError(
            f"{path.name} contradicts itself or earlier decisions",
            [*problems, "nothing was recorded"],
        )
    store.save_decisions(new)
    return DecideResult(
        review_id=review_id,
        reviewer=reviewer,
        same=sum(decision.decision == SAME for decision in new),
        different=sum(decision.decision != SAME for decision in new),
        unchanged=unchanged,
        pending=pending,
        groups=len(set(group_of.values())),
    )
