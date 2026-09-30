"""Reading a review's protocol from the workspace: one way in, for every feature that needs it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lrcc.domain.errors import ProtocolError, ReviewError
from lrcc.domain.protocol import Protocol, parse_protocol, protocol_digest
from lrcc.domain.workspace import Workspace


@dataclass(frozen=True)
class LoadedProtocol:
    """A validated protocol, where it was read from, and the digest of its exact bytes."""

    protocol: Protocol
    path: Path
    sha256: str


def load_review_protocol(workspace: Workspace, review_id: str) -> LoadedProtocol:
    """Read and validate the protocol of ``review_id``.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol to read.

    Returns:
        The protocol, its path and its digest.

    Raises:
        ReviewError: If the id is invalid or the review has no protocol.
        ProtocolError: If the protocol is invalid, or names another review than its folder.
    """
    path = workspace.protocol_path(review_id)
    if not path.is_file():
        raise ReviewError(
            f"review {review_id!r} has no protocol at {path}",
            [f"create the review first with: lrcc init {review_id}"],
        )
    data = path.read_bytes()
    protocol = parse_protocol(data, source=str(path))
    if protocol.review_id != review_id:
        raise ProtocolError(
            f"{path} names the review {protocol.review_id!r}, but lives in the folder of"
            f" {review_id!r}",
            ["the review_id inside a protocol must match its folder"],
        )
    return LoadedProtocol(protocol, path, protocol_digest(data))
