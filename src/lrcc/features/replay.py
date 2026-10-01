"""Rederive every run's records from its stored responses, without the network (ADR-0013).

A replay reads the raw responses a run stored and derives the records again with the code as it
is now. If they are the records the run logged, the run is reproduced. If they are not, the code
changed what it derives from the same answers, and the replay says by how much. A replay never
asks a source anything: querying again is a re-run, which is a new run.

A search's answers are read by its source's adapter; an import's files by the RIS reader, which
needs no adapter at all (ADR-0016).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from lrcc.domain.record import Record
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.ris import read_ris
from lrcc.domain.runs import Run, records_digest, sha256_hex
from lrcc.domain.workspace import Workspace
from lrcc.ports.source import Source
from lrcc.ports.store import ReviewStore

#: What derives a run's records from its stored responses.
_Derive = Callable[[Sequence[bytes]], tuple[Record, ...]]


@dataclass(frozen=True)
class ReplayedRun:
    """One run replayed: what it logged, what the replay derived, and why it failed, if it did."""

    run_id: str
    logged: int
    replayed: int | None
    identical: bool
    problem: str | None


@dataclass(frozen=True)
class ReplayResult:
    """Every run of a review, replayed."""

    review_id: str
    runs: tuple[ReplayedRun, ...]

    @property
    def identical(self) -> bool:
        """Whether every run was reproduced exactly."""
        return all(run.identical for run in self.runs)

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "identical": self.identical,
            "runs": [
                {
                    "run_id": run.run_id,
                    "logged": run.logged,
                    "replayed": run.replayed,
                    "identical": run.identical,
                    "problem": run.problem,
                }
                for run in self.runs
            ],
        }


def _deriver(run: Run, sources: Mapping[str, Source]) -> _Derive | None:
    if run.imported is None:
        source = sources.get(run.source)
        return None if source is None else source.records_from
    names = [response.file for response in run.responses]

    def read_exports(bodies: Sequence[bytes]) -> tuple[Record, ...]:
        return tuple(
            record
            for body, name in zip(bodies, names, strict=True)
            for record in read_ris(body, run.source, name)
        )

    return read_exports


def _replay(run: Run, store: ReviewStore, sources: Mapping[str, Source]) -> ReplayedRun:
    derive = _deriver(run, sources)
    if derive is None:
        return ReplayedRun(
            run.run_id, run.retrieved, None, False, f"no adapter for the source {run.source}"
        )
    bodies = []
    for response in run.responses:
        body = store.read_response(run.run_id, response.file)
        if body is None or sha256_hex(body) != response.sha256:
            state = "is missing" if body is None else "does not match the digest in the log"
            return ReplayedRun(
                run.run_id, run.retrieved, None, False, f"{response.file} {state}; run verify"
            )
        bodies.append(body)
    records = derive(bodies)
    identical = records_digest(records) == run.records_sha256
    return ReplayedRun(
        run.run_id,
        run.retrieved,
        len(records),
        identical,
        None if identical else "the records derived now differ from the ones logged",
    )


def replay_review(
    workspace: Workspace, review_id: str, store: ReviewStore, sources: Mapping[str, Source]
) -> ReplayResult:
    """Replay every run of ``review_id`` from its stored responses.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose runs to replay.
        store: The review's storage.
        sources: The adapters that can derive records, by source name. None is asked anything.

    Returns:
        For each run, whether the records derived now are the ones it logged.

    Raises:
        ReviewError: If the id is invalid or the review has no protocol.
        ProtocolError: If the protocol is invalid.
        StoreError: If the log cannot be read.
        SourceError: If a stored response cannot be read as records.
    """
    load_review_protocol(workspace, review_id)
    return ReplayResult(
        review_id, tuple(_replay(logged.run, store, sources) for logged in store.log())
    )
