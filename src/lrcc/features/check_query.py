"""Test a search string against a gold set, one source at a time (ADR-0014).

For every work known to be relevant, ``check-query`` asks the source two questions: does it index
the work at all, and does the protocol's string retrieve it. The answers give one of four states,
and only one of them is the string's fault:

- retrieved: the string finds the work;
- missed: the source indexes the work and the string does not find it;
- not indexed: the source does not hold the work, which is coverage, not the string;
- unknown: the work has no identifier this source can look up.

Nothing is stored. A check asks about a handful of works; it is not a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lrcc.domain.errors import ReviewError
from lrcc.domain.gold import GoldWork
from lrcc.domain.reviews import load_gold_set, load_review_protocol
from lrcc.domain.runs import sha256_hex
from lrcc.domain.workspace import Workspace
from lrcc.ports.source import Source


class GoldState(StrEnum):
    """What a source and a string did with one work of the gold set."""

    retrieved = "retrieved"
    missed = "missed"
    not_indexed = "not indexed"
    unknown = "unknown"


@dataclass(frozen=True)
class WorkCheck:
    """One gold work, and its state for one source."""

    work: GoldWork
    state: GoldState


@dataclass(frozen=True)
class CheckResult:
    """A search string checked against a gold set, for one source."""

    review_id: str
    source: str
    query: str
    protocol_sha256: str
    checks: tuple[WorkCheck, ...]

    def count(self, state: GoldState) -> int:
        """Return how many works are in ``state``."""
        return sum(1 for check in self.checks if check.state is state)

    @property
    def complete(self) -> bool:
        """Whether the string retrieves every work the source indexes."""
        return self.count(GoldState.missed) == 0

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "source": self.source,
            "query_sha256": sha256_hex(self.query.encode()),
            "protocol_sha256": self.protocol_sha256,
            "complete": self.complete,
            "counts": {state.value: self.count(state) for state in GoldState},
            "works": [
                {
                    "label": check.work.label,
                    "doi": check.work.doi,
                    "pmid": check.work.pmid,
                    "arxiv": check.work.arxiv,
                    "state": check.state.value,
                }
                for check in self.checks
            ],
        }


def _state(source: Source, work: GoldWork, query: str) -> GoldState:
    indexed = source.holds(work, None)
    if indexed is None:
        return GoldState.unknown
    if not indexed:
        return GoldState.not_indexed
    return GoldState.retrieved if source.holds(work, query) else GoldState.missed


def check_query(workspace: Workspace, review_id: str, source: Source) -> CheckResult:
    """Check the protocol's string for ``source`` against the review's gold set.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol and gold set to use.
        source: The source to ask.

    Returns:
        The state of every gold work for this source and string.

    Raises:
        ReviewError: If the review has no protocol, no string for the source, or no valid gold set.
        ProtocolError: If the protocol is invalid.
        NetworkError: If a request is refused or fails.
        SourceError: If an answer cannot be read.
    """
    loaded = load_review_protocol(workspace, review_id)
    entry = loaded.protocol.sources.get(source.name)
    if entry is None:
        raise ReviewError(
            f"the protocol of {review_id!r} has no search string for {source.name}",
            [f"its sources are: {', '.join(sorted(loaded.protocol.sources))}"],
        )
    gold, _ = load_gold_set(workspace, review_id)
    return CheckResult(
        review_id=review_id,
        source=source.name,
        query=entry.query,
        protocol_sha256=loaded.sha256,
        checks=tuple(WorkCheck(work, _state(source, work, entry.query)) for work in gold.works),
    )
