"""Title and abstract screening: decisions on groups, their order, the pilot and the chain.

A person screens each group of a review (ADR-0018) by its title and abstract: include, exclude
with one of the protocol's exclusion codes, or uncertain, which goes on to full text. Decisions
are appended to a hash-chained log. A group's decision is the latest made on any of its works,
so a correction is a new entry (ADR-0019).

The order looks random but stores nothing: each group's place is the SHA-256 of the review id
and its ``work_id``. The pilot is the first 50 groups of that order, plus the frontier cases.

Everything here is pure; reading and writing is the features' job.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from lrcc.domain.errors import ReviewError
from lrcc.domain.gold import GoldSet
from lrcc.domain.runs import ChainLink, canonical, link_problems

INCLUDE: Final = "include"
EXCLUDE: Final = "exclude"
UNCERTAIN: Final = "uncertain"
Verdict = Literal["include", "exclude", "uncertain"]
VERDICTS: tuple[Verdict, ...] = (INCLUDE, EXCLUDE, UNCERTAIN)

#: How many groups of the order the pilot takes, before the frontier cases (ADR-0019).
PILOT_SIZE = 50


class ScreenDecision(BaseModel):
    """A person's title and abstract decision on a group, named by one of its works."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_id: str
    decision: Verdict
    code: str | None
    note: str
    pilot: bool
    protocol_sha256: str
    reviewer: str
    decided_at: str

    def entry(self) -> str:
        """Return the decision as the canonical JSON document the log stores and hashes."""
        return canonical(self.model_dump(mode="json"))


class LoggedScreen(BaseModel):
    """A screening decision as read back from the log, with its place in the chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ScreenDecision
    entry: str
    prev_hash: str
    entry_hash: str


def order_key(review_id: str, work_id: str) -> str:
    """Return a group's place in the screening order: the SHA-256 of ``review_id|work_id``."""
    return hashlib.sha256(f"{review_id}|{work_id}".encode()).hexdigest()


def screening_order(review_id: str, groups: Iterable[str]) -> list[str]:
    """Order groups as screening presents them: random-looking, reproducible, stateless.

    Args:
        review_id: The review, part of every key, so two reviews order the same works apart.
        groups: The groups to order, by name.

    Returns:
        The groups sorted by :func:`order_key`.
    """
    return sorted(groups, key=lambda work_id: order_key(review_id, work_id))


def frontier_groups(
    frontier: GoldSet, identifiers: Mapping[str, str], group_of: Mapping[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Find the frontier cases among the review's groups, by their identifiers.

    Args:
        frontier: The frontier cases, in the gold set's format.
        identifiers: The catalog's typed identifiers, each with its work.
        group_of: Every work of the review, with its group.

    Returns:
        The group of each case found, by label; and the labels of the cases not found.
    """
    found: dict[str, str] = {}
    missing: list[str] = []
    for work in frontier.works:
        keys = [
            f"{kind}:{value}"
            for kind, value in (("doi", work.doi), ("pmid", work.pmid), ("arxiv", work.arxiv))
            if value
        ]
        groups = [group_of[identifiers[key]] for key in keys if identifiers.get(key) in group_of]
        if groups:
            found[work.label] = groups[0]
        else:
            missing.append(work.label)
    return found, missing


def pilot_groups(order: Sequence[str], frontier: Iterable[str]) -> list[str]:
    """Return the pilot: the first groups of the order, then any frontier case not among them.

    Args:
        order: Every group to screen, in screening order.
        frontier: The groups of the frontier cases found.

    Returns:
        The pilot's groups, in screening order.
    """
    chosen = set(order[:PILOT_SIZE]) | set(frontier)
    return [group for group in order if group in chosen]


def screened(log: Sequence[LoggedScreen], group_of: Mapping[str, str]) -> dict[str, ScreenDecision]:
    """Return each group's decision in force: the latest made on any of its works.

    Args:
        log: The screening log, in order.
        group_of: Every work of the review, with its group.

    Returns:
        The decision of every decided group, by group. Decisions on works the review no longer
        holds are left out.
    """
    found: dict[str, ScreenDecision] = {}
    for logged in log:
        group = group_of.get(logged.decision.work_id)
        if group is not None:
            found[group] = logged.decision
    return found


def check_verdict(verdict: str, code: str | None, exclusion: Mapping[str, str]) -> None:
    """Refuse a decision a protocol cannot carry: an exclusion needs one of its codes.

    Args:
        verdict: ``include``, ``exclude`` or ``uncertain``.
        code: The exclusion code, or None.
        exclusion: The protocol's exclusion codes, with their text.

    Raises:
        ReviewError: If the verdict is unknown, an exclusion has no code or an unknown one, or
            another verdict carries a code.
    """
    if verdict not in VERDICTS:
        raise ReviewError(
            f"{verdict!r} is not a decision", ["decide include, exclude or uncertain"]
        )
    if verdict == EXCLUDE and code not in exclusion:
        raise ReviewError(
            f"an exclusion needs one of the protocol's codes, not {code!r}",
            [f"the codes are: {', '.join(exclusion)}"],
        )
    if verdict != EXCLUDE and code is not None:
        raise ReviewError(f"only an exclusion cites a code; {verdict} does not take {code!r}")


def screening_chain_problems(log: Sequence[LoggedScreen]) -> list[str]:
    """Recompute the screening log's chain, as for runs (ADR-0012), and name what does not hold.

    Args:
        log: The screening decisions, in order.

    Returns:
        One line per entry whose link, hash or canonical form does not match.
    """
    return link_problems(
        [
            ChainLink(
                f"screening {number} ({logged.decision.work_id})",
                logged.entry,
                logged.prev_hash,
                logged.entry_hash,
                logged.decision.entry(),
            )
            for number, logged in enumerate(log, start=1)
        ]
    )
