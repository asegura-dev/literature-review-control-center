"""Composition: the one place the view builds adapters from the configuration (ADR-0003).

The view is the driving adapter, so constructing the HTTP client and a source, and handing them
to a feature, is its job. No other view module may import ``adapters``.
"""

from __future__ import annotations

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.arxiv import ArxivSource
from lrcc.adapters.sources.pubmed import PubMedSource
from lrcc.adapters.storage.duckdb_store import DuckDbReviewStore
from lrcc.domain.config import Config
from lrcc.domain.workspace import Workspace

_SOURCES: dict[str, type[ArxivSource] | type[PubMedSource]] = {
    ArxivSource.name: ArxivSource,
    PubMedSource.name: PubMedSource,
}

#: The sources that have an adapter, in the order the command offers them.
SOURCE_NAMES = tuple(sorted(_SOURCES))


def build_source(name: str, config: Config) -> ArxivSource | PubMedSource:
    """Build the source ``name`` over an HTTP client limited by the configuration.

    Args:
        name: One of :data:`SOURCE_NAMES`.
        config: The validated configuration, whose network settings bound the client.

    Returns:
        The source, ready to search.
    """
    return _SOURCES[name](HttpClient(config.network))


def build_store(workspace: Workspace, review_id: str) -> DuckDbReviewStore:
    """Build the storage of one review. Nothing is opened until the store is used.

    Args:
        workspace: The accepted workspace.
        review_id: The review whose storage to build.

    Returns:
        The store, over the review's folder inside the workspace.

    Raises:
        ReviewError: If the id is not a valid review id.
        WorkspaceError: If the review's folder would leave the workspace.
    """
    return DuckDbReviewStore(workspace.review_dir(review_id))
