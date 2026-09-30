"""Report where a review stands: its protocol, its runs and the state of its log (ADR-0012).

``status`` recomputes the hash chain of the run log every time it is asked, so an edited log is
reported the next time anyone looks.
"""

from __future__ import annotations

from dataclasses import dataclass

from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.runs import LoggedRun, chain_problems
from lrcc.domain.workspace import Workspace
from lrcc.ports.store import ReviewStore


@dataclass(frozen=True)
class RunSummary:
    """One run, and whether it used the protocol as it stands now."""

    logged: LoggedRun
    current_protocol: bool


@dataclass(frozen=True)
class StatusResult:
    """A review's protocol digest, its runs, and what is wrong with its log, if anything."""

    review_id: str
    protocol_sha256: str
    runs: tuple[RunSummary, ...]
    chain_problems: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the status as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "protocol_sha256": self.protocol_sha256,
            "chain_intact": not self.chain_problems,
            "chain_problems": list(self.chain_problems),
            "runs": [
                {
                    "run_id": summary.logged.run.run_id,
                    "started_at": summary.logged.run.started_at,
                    "source": summary.logged.run.source,
                    "reported": summary.logged.run.reported,
                    "retrieved": summary.logged.run.retrieved,
                    "complete": summary.logged.run.complete,
                    "current_protocol": summary.current_protocol,
                    "entry_hash": summary.logged.entry_hash,
                }
                for summary in self.runs
            ],
        }


def review_status(workspace: Workspace, review_id: str, store: ReviewStore) -> StatusResult:
    """Report the runs of ``review_id`` and the state of its log.

    Args:
        workspace: The accepted workspace.
        review_id: The review to report on.
        store: The review's storage.

    Returns:
        The protocol's digest, every run, and the problems found in the hash chain.

    Raises:
        ReviewError: If the id is invalid or the review has no protocol.
        ProtocolError: If the protocol is invalid.
        StoreError: If the log cannot be read.
    """
    loaded = load_review_protocol(workspace, review_id)
    log = store.log()
    return StatusResult(
        review_id=review_id,
        protocol_sha256=loaded.sha256,
        runs=tuple(
            RunSummary(logged, logged.run.protocol_sha256 == loaded.sha256) for logged in log
        ),
        chain_problems=tuple(chain_problems(log)),
    )
