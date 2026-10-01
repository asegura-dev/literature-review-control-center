"""Fuzzy duplicates: candidate pairs by title, and the decisions a person makes (ADR-0018).

Exact deduplication joins records that share an identifier (ADR-0017). Works it leaves apart may
still be one publication, typically an arXiv preprint beside its published version. Their titles
are scored, and a pair at or above the threshold is proposed to a person, who decides ``same``
or ``different``. Decisions are appended to a hash-chained log. Works joined by ``same`` form a
group, the unit a review counts.

Scoring, grouping and the chain are pure; reading and writing them is the features' job.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from lrcc.domain.record import Record
from lrcc.domain.runs import ChainLink, canonical, link_problems
from lrcc.domain.works import Link, normalize_title

#: The default threshold, measured on the first review's real records (v0.9.0 phase notes). It
#: keeps a preprint retitled on publication (0.82) and lets through a few pairs a person rejects.
CANDIDATE_MIN = 0.80

SAME: Final = "same"
DIFFERENT: Final = "different"
Verdict = Literal["same", "different"]

#: How a group's name is chosen: the published version over the preprint (the brief).
_RANK = ("doi", "pmid", "arxiv")
#: Every character a normalized title can hold (``works.normalize_title``).
_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 "


@dataclass(frozen=True)
class WorkFacts:
    """What a person sees of a work, and the titles its pairs are scored on."""

    work_id: str
    titles: tuple[str, ...]
    title: str
    first_author: str
    year: int | None
    sources: tuple[str, ...]
    doi: str | None


@dataclass(frozen=True)
class Candidate:
    """Two works whose titles score at or above the threshold, ``work_a`` sorting first."""

    work_a: str
    work_b: str
    score: float


class PairDecision(BaseModel):
    """A person's decision on two works: one publication, or two (ADR-0018)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_a: str
    work_b: str
    decision: Verdict
    score: float
    note: str
    reviewer: str
    decided_at: str

    def entry(self) -> str:
        """Return the decision as the canonical JSON document the log stores and hashes."""
        return canonical(self.model_dump(mode="json"))


class LoggedDecision(BaseModel):
    """A decision as read back from the log, with its place in the chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: PairDecision
    entry: str
    prev_hash: str
    entry_hash: str


def pair_of(first: str, second: str) -> tuple[str, str]:
    """Return two ``work_id``s in their canonical order, the smaller first."""
    return (first, second) if first < second else (second, first)


def score(first: Sequence[str], second: Sequence[str], floor: float = 0.0) -> float:
    """Return the best similarity between two works' normalized titles, to three decimals.

    Args:
        first: One work's normalized titles.
        second: The other's.
        floor: Pairs that cannot reach it are not computed in full; they score 0.

    Returns:
        The highest ``difflib.SequenceMatcher`` ratio over every pair of titles, or 0. The
        matcher's ``autojunk`` is off: from 200 characters on, it drops a text's most frequent
        characters, and a long title nearly equal to another scored 0.2 instead of 0.97.
    """
    best = 0.0
    for one in first:
        for other in second:
            matcher = SequenceMatcher(None, one, other, autojunk=False)
            bound = max(best, floor)
            if matcher.real_quick_ratio() < bound or matcher.quick_ratio() < bound:
                continue
            best = max(best, matcher.ratio())
    return round(best, 3) if best >= floor else 0.0


def work_facts(linked: Sequence[tuple[Link, Record]]) -> dict[str, WorkFacts]:
    """Gather each work's records, in log order, into what is scored and shown.

    Args:
        linked: Every link with its record, in log order.

    Returns:
        The facts of every work the links name, by ``work_id``, in the order works first appear.
    """
    records: dict[str, list[Record]] = {}
    for link, record in linked:
        records.setdefault(link.work_id, []).append(record)
    facts = {}
    for work_id, own in records.items():
        first = own[0]
        titles = tuple(dict.fromkeys(t for t in (normalize_title(r.title) for r in own) if t))
        facts[work_id] = WorkFacts(
            work_id=work_id,
            titles=titles,
            title=first.title,
            first_author=first.authors[0] if first.authors else "",
            year=first.year,
            sources=tuple(sorted({record.source for record in own})),
            doi=next((record.doi for record in own if record.doi), None),
        )
    return facts


def current_decisions(log: Sequence[LoggedDecision]) -> dict[tuple[str, str], PairDecision]:
    """Return each pair's decision in force: the latest one recorded.

    Args:
        log: The decisions, in log order.

    Returns:
        The latest decision of every pair, by its ordered ``work_id``s.
    """
    return {(logged.decision.work_a, logged.decision.work_b): logged.decision for logged in log}


def groups(
    order: Sequence[str],
    identities: Mapping[str, str],
    decisions: Mapping[tuple[str, str], PairDecision],
) -> dict[str, str]:
    """Join works by ``same`` decisions, and name each group by the work it keeps.

    Args:
        order: The review's works, in the order the catalog named them.
        identities: Each work's identity, such as ``doi:...``.
        decisions: The decisions in force.

    Returns:
        Every work's group, named by the work with a DOI-based identity, then PMID, then arXiv,
        then the first named.
    """
    parent = {work_id: work_id for work_id in order}

    def root(work_id: str) -> str:
        while parent[work_id] != work_id:
            parent[work_id] = parent[parent[work_id]]
            work_id = parent[work_id]
        return work_id

    for (first, second), decision in decisions.items():
        if decision.decision == SAME and first in parent and second in parent:
            parent[root(first)] = root(second)
    members: dict[str, list[str]] = {}
    for work_id in order:
        members.setdefault(root(work_id), []).append(work_id)
    position = {work_id: index for index, work_id in enumerate(order)}

    def rank(work_id: str) -> tuple[int, int]:
        kind = identities.get(work_id, "").split(":", 1)[0]
        return (_RANK.index(kind) if kind in _RANK else len(_RANK), position[work_id])

    named = {}
    for group in members.values():
        keeper = min(group, key=rank)
        named.update(dict.fromkeys(group, keeper))
    return named


def contradictions(
    group_of: Mapping[str, str], decisions: Mapping[tuple[str, str], PairDecision]
) -> list[str]:
    """Name every ``different`` decision whose works ``same`` decisions have joined.

    Args:
        group_of: Every work's group.
        decisions: The decisions in force.

    Returns:
        One line per contradiction; empty if there is none.
    """
    return [
        f"{first} and {second} are decided different, but same decisions join them"
        for (first, second), decision in sorted(decisions.items())
        if decision.decision == DIFFERENT
        and first in group_of
        and group_of.get(first) == group_of.get(second)
    ]


def candidate_pairs(
    facts: Mapping[str, WorkFacts],
    group_of: Mapping[str, str],
    decided: set[tuple[str, str]],
    minimum: float,
) -> list[Candidate]:
    """Find the pairs of works a person should judge.

    Args:
        facts: Every work of the review.
        group_of: Every work's group; works of one group are never a pair.
        decided: Pairs already decided, which are not proposed again.
        minimum: The lowest score proposed.

    Returns:
        The pairs, highest score first, then by ``work_id``.
    """
    works = list(facts.values())
    bags = {
        title: tuple(title.count(character) for character in _ALPHABET)
        for work in works
        for title in work.titles
    }
    found = []
    for index, other in enumerate(works):
        # One matcher per title of the later work: SequenceMatcher caches what it learns about
        # its second sequence, so every earlier work is compared against it cheaply. The
        # orientation is the one ``pair_score`` uses, so a listed score is the recorded one.
        matchers = [
            (SequenceMatcher(None, "", title, autojunk=False), title) for title in other.titles
        ]
        for one in works[:index]:
            key = pair_of(one.work_id, other.work_id)
            if group_of[one.work_id] == group_of[other.work_id] or key in decided:
                continue
            best = 0.0
            for title in one.titles:
                for matcher, later in matchers:
                    bound = max(best, minimum) * (len(title) + len(later))
                    # Two upper bounds of the ratio, cheapest first: the lengths, as
                    # real_quick_ratio, then the shared characters, as quick_ratio, from counts
                    # made once. Normalized titles hold only the alphabet's characters, so the
                    # second is exact. Only pairs that pass get the full, costly ratio.
                    if 2 * min(len(title), len(later)) < bound:
                        continue
                    if 2 * sum(map(min, bags[title], bags[later])) < bound:
                        continue
                    matcher.set_seq1(title)
                    best = max(best, matcher.ratio())
            if best >= minimum:
                found.append(Candidate(key[0], key[1], round(best, 3)))
    return sorted(found, key=lambda pair: (-pair.score, pair.work_a, pair.work_b))


def pair_score(facts: Mapping[str, WorkFacts], first: str, second: str) -> float:
    """Score two works as ``candidate_pairs`` does: the earlier work's titles against the later's.

    ``difflib``'s ratio is not quite symmetric, so the orientation is fixed by the order works
    first appear in, and a decision records the very score its pair was listed with.

    Args:
        facts: Every work of the review, in the order they first appear.
        first: One ``work_id``.
        second: The other.

    Returns:
        The score, to three decimals.
    """
    position = {work_id: index for index, work_id in enumerate(facts)}
    earlier, later = sorted((first, second), key=position.__getitem__)
    return score(facts[earlier].titles, facts[later].titles)


def decision_chain_problems(log: Sequence[LoggedDecision]) -> list[str]:
    """Recompute the decisions' chain and name what does not hold, as for runs (ADR-0012).

    Args:
        log: The decisions, in log order.

    Returns:
        One line per entry whose link, hash or canonical form does not match.
    """
    return link_problems(
        [
            ChainLink(
                f"decision {number} ({logged.decision.work_a} / {logged.decision.work_b})",
                logged.entry,
                logged.prev_hash,
                logged.entry_hash,
                logged.decision.entry(),
            )
            for number, logged in enumerate(log, start=1)
        ]
    )
