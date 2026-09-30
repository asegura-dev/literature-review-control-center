"""Check a review's protocol and report its digest (ADR-0010).

``validate`` reads ``reviews/<review_id>/protocol.yaml``, checks every field, and reports what the
protocol holds together with the SHA-256 of its exact bytes: the digest a person registers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lrcc.domain.reviews import load_review_protocol
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
    loaded = load_review_protocol(workspace, review_id)
    protocol = loaded.protocol
    return ValidationResult(
        review_id=review_id,
        protocol=loaded.path,
        sha256=loaded.sha256,
        title=protocol.title,
        inclusion=protocol.inclusion,
        exclusion=protocol.exclusion,
        sources=tuple(sorted(protocol.sources)),
        extraction=tuple(field.name for field in protocol.extraction),
    )
