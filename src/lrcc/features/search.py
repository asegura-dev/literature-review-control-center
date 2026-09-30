"""Run a review's search string against one source (ADR-0011).

``search`` reads the protocol, takes the string written for the chosen source, and asks the
source for records. It stores nothing: raw responses and runs arrive in v0.5.0. Until then a
search is a preview of what a string returns, and must not be reported as a run.
"""

from __future__ import annotations

from dataclasses import dataclass

from lrcc.domain.errors import ReviewError
from lrcc.domain.record import SearchResult
from lrcc.domain.reviews import load_review_protocol
from lrcc.domain.workspace import Workspace
from lrcc.ports.source import Source


@dataclass(frozen=True)
class SearchOutcome:
    """What a search returned, and the digest of the protocol whose string was run."""

    review_id: str
    protocol_sha256: str
    result: SearchResult

    def as_dict(self) -> dict[str, object]:
        """Return the outcome as JSON-ready data."""
        return {
            "review_id": self.review_id,
            "protocol_sha256": self.protocol_sha256,
            "source": self.result.source,
            "query": self.result.query,
            "reported": self.result.reported,
            "retrieved": len(self.result.records),
            "stored": False,
            "records": [record.model_dump(mode="json") for record in self.result.records],
        }


def search_review(
    workspace: Workspace, review_id: str, source: Source, limit: int
) -> SearchOutcome:
    """Run the search string ``review_id`` holds for ``source``.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose protocol names the search string.
        source: The source to ask.
        limit: The most records to retrieve.

    Returns:
        The source's reported count and the records retrieved.

    Raises:
        ReviewError: If the review has no protocol, or the protocol has no string for the source.
        ProtocolError: If the protocol is invalid.
        NetworkError: If a request is refused or fails.
        SourceError: If the source's answer cannot be read.
    """
    loaded = load_review_protocol(workspace, review_id)
    entry = loaded.protocol.sources.get(source.name)
    if entry is None:
        raise ReviewError(
            f"the protocol of {review_id!r} has no search string for {source.name}",
            [f"its sources are: {', '.join(sorted(loaded.protocol.sources))}"],
        )
    return SearchOutcome(review_id, loaded.sha256, source.search(entry.query, limit))
