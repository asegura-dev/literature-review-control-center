"""Check a review's protocol and report its digest (ADR-0010).

``validate`` reads ``reviews/<review_id>/protocol.yaml``, checks every field, and reports what the
protocol holds together with the SHA-256 of its exact bytes: the digest a person registers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lrcc.domain.errors import ProtocolError, ReviewError
from lrcc.domain.protocol import parse_protocol, protocol_digest
from lrcc.domain.workspace import Workspace


@dataclass(frozen=True)
class ValidationResult:
    """What a valid protocol holds."""

    review_id: str
    protocol: Path
    sha256: str
    title: str
    inclusion: tuple[str, ...]
    exclusion: tuple[str, ...]
    sources: tuple[str, ...]
    extraction: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the result as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "protocol": str(self.protocol),
            "sha256": self.sha256,
            "title": self.title,
            "criteria": {"inclusion": list(self.inclusion), "exclusion": list(self.exclusion)},
            "sources": list(self.sources),
            "extraction": list(self.extraction),
        }


def validate_review(workspace: Workspace, review_id: str) -> ValidationResult:
    """Validate the protocol of ``review_id``.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol to check.

    Returns:
        What the protocol holds, and its digest.

    Raises:
        ReviewError: If the id is invalid or the review has no protocol.
        ProtocolError: If the protocol is invalid, listing every problem, or if it names another
            review than the folder it lives in.
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
    return ValidationResult(
        review_id=review_id,
        protocol=path,
        sha256=protocol_digest(data),
        title=protocol.title,
        inclusion=protocol.inclusion,
        exclusion=protocol.exclusion,
        sources=tuple(sorted(protocol.sources)),
        extraction=tuple(field.name for field in protocol.extraction),
    )
