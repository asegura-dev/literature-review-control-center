"""Check that what a review stores is what its log says (ADR-0013).

``verify`` trusts nothing it reads. It recomputes the hash chain, the SHA-256 and size of every
raw response on disk, and the digest of the records in the database, and compares each with the
log. It also reports what the log does not know about: a file or a run folder nobody logged.
The chains of a person's decisions, on candidate pairs (ADR-0018) and on screening (ADR-0019),
are recomputed too, and every kept protocol is checked against the digest it is named by.
"""

from __future__ import annotations

from dataclasses import dataclass

from lrcc.domain.fuzzy import decision_chain_problems
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.runs import chain_problems, records_digest, sha256_hex
from lrcc.domain.screening import screening_chain_problems
from lrcc.domain.workspace import Workspace
from lrcc.ports.store import ReviewStore


@dataclass(frozen=True)
class VerifyResult:
    """How much was checked, and everything that does not match."""

    review_id: str
    runs: int
    responses: int
    problems: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "runs": self.runs,
            "responses": self.responses,
            "verified": not self.problems,
            "problems": list(self.problems),
        }


def verify_review(workspace: Workspace, review_id: str, store: ReviewStore) -> VerifyResult:
    """Compare everything ``review_id`` stores with its run log.

    Args:
        workspace: The accepted workspace.
        review_id: The review to check.
        store: The review's storage.

    Returns:
        The number of runs and responses checked, and every problem found.

    Raises:
        ReviewError: If the id is invalid or the review has no protocol.
        ProtocolError: If the protocol is invalid.
        StoreError: If the log cannot be read, or names a file outside the review.
    """
    load_review_protocol(workspace, review_id)
    log = store.log()
    on_disk = store.files_on_disk()
    problems = list(chain_problems(log))
    responses = 0
    for logged in log:
        run = logged.run
        for response in run.responses:
            responses += 1
            where = f"{run.run_id}/{response.file}"
            body = store.read_response(run.run_id, response.file)
            if body is None:
                problems.append(f"{where}: is missing")
            elif sha256_hex(body) != response.sha256 or len(body) != response.size:
                problems.append(f"{where}: does not match the digest in the log")
        logged_files = {response.file for response in run.responses}
        problems.extend(
            f"{run.run_id}/{name}: is not named by the log"
            for name in on_disk.get(run.run_id, ())
            if name not in logged_files
        )
        if records_digest(store.records(run.run_id)) != run.records_sha256:
            problems.append(f"{run.run_id}: the records in the database do not match the log")
    logged_runs = {logged.run.run_id for logged in log}
    problems.extend(
        f"runs/{folder}: no log entry names this folder"
        for folder in on_disk
        if folder not in logged_runs
    )
    problems.extend(decision_chain_problems(store.decisions()))
    problems.extend(screening_chain_problems(store.screenings()))
    problems.extend(
        f"protocols/{name}: its content does not match its name"
        for name, data in store.protocols().items()
        if name != f"{sha256_hex(data)}.yaml"
    )
    return VerifyResult(review_id, len(log), responses, tuple(problems))
