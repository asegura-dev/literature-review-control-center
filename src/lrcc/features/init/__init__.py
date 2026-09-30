"""Create a review in the workspace from the protocol template (ADR-0010).

``init`` writes ``reviews/<review_id>/protocol.yaml``, a synthetic example for a person to replace
with the real review's protocol. It never overwrites: if the review exists, nothing is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from lrcc.domain.errors import ReviewError
from lrcc.domain.identifiers import require_review_id
from lrcc.domain.protocol import protocol_digest
from lrcc.domain.workspace import LIBRARY, REVIEWS, Workspace

TEMPLATE = "protocol-template.yaml"
_PLACEHOLDER = b"__REVIEW_ID__"


@dataclass(frozen=True)
class InitResult:
    """What ``init`` created."""

    review_id: str
    protocol: Path
    sha256: str

    def as_dict(self) -> dict[str, str]:
        """Return the result as JSON-ready data."""
        return {"review_id": self.review_id, "protocol": str(self.protocol), "sha256": self.sha256}


def init_review(workspace: Workspace, review_id: str) -> InitResult:
    """Create the review ``review_id`` with the protocol template.

    Args:
        workspace: The accepted workspace.
        review_id: The new review's id.

    Returns:
        Where the protocol was written, and its digest.

    Raises:
        ReviewError: If the id is invalid, or the review already exists.
        WorkspaceError: If a path would leave the workspace.
    """
    require_review_id(review_id)
    for folder in (LIBRARY, REVIEWS):
        workspace.resolve_within(folder).mkdir(exist_ok=True)
    review_dir = workspace.review_dir(review_id)
    if review_dir.exists():
        raise ReviewError(
            f"review {review_id!r} already exists at {review_dir}",
            ["nothing was changed; choose another id, or remove that folder yourself"],
        )
    template = files(__name__).joinpath(TEMPLATE).read_bytes()
    data = template.replace(_PLACEHOLDER, review_id.encode("ascii"))
    review_dir.mkdir()
    protocol = workspace.protocol_path(review_id)
    protocol.write_bytes(data)
    return InitResult(review_id, protocol, protocol_digest(data))
