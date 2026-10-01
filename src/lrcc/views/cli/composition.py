"""Composition: the one place the view builds adapters from the configuration (ADR-0003).

The view is the driving adapter, so constructing the HTTP client and a source, and handing them
to a feature, is its job. No other view module may import ``adapters``.
"""

from __future__ import annotations

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.arxiv import ArxivSource
from lrcc.adapters.sources.ieee import IeeeSource
from lrcc.adapters.sources.pubmed import PubMedSource
from lrcc.adapters.sources.scopus import ScopusSource
from lrcc.adapters.storage.duckdb_catalog import CATALOG, DuckDbWorkCatalog
from lrcc.adapters.storage.duckdb_store import DuckDbReviewStore
from lrcc.domain.config import Config
from lrcc.domain.secrets import Secrets
from lrcc.domain.workspace import LIBRARY, Workspace

AnySource = ArxivSource | IeeeSource | PubMedSource | ScopusSource

_SOURCES: dict[str, type[AnySource]] = {
    source.name: source for source in (ArxivSource, IeeeSource, PubMedSource, ScopusSource)
}

#: The sources that have an adapter, in the order the command offers them.
SOURCE_NAMES = tuple(sorted(_SOURCES))


def build_source(name: str, config: Config, secrets: Secrets) -> AnySource:
    """Build the source ``name`` over an HTTP client limited by the configuration.

    Args:
        name: One of :data:`SOURCE_NAMES`.
        config: The validated configuration, whose network settings bound the client.
        secrets: The run's keys; a source asks for its own only when it makes a request.

    Returns:
        The source, ready to search.
    """
    return _SOURCES[name](HttpClient(config.network), secrets)


def build_sources(config: Config, secrets: Secrets) -> dict[str, AnySource]:
    """Build every source, over one HTTP client limited by the configuration.

    A replay uses the sources only to derive records from stored answers, so nothing is
    requested, whatever the network settings say.

    Args:
        config: The validated configuration.
        secrets: The run's keys. A replay makes no request, so none is required.

    Returns:
        The sources, by name.
    """
    client = HttpClient(config.network)
    return {name: source(client, secrets) for name, source in _SOURCES.items()}


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


def build_catalog(workspace: Workspace) -> DuckDbWorkCatalog:
    """Build the workspace's work catalog, ``library/catalog.duckdb`` (ADR-0006).

    Args:
        workspace: The accepted workspace.

    Returns:
        The catalog. Nothing is opened until it is used.

    Raises:
        WorkspaceError: If the library folder would leave the workspace.
    """
    return DuckDbWorkCatalog(workspace.resolve_within(LIBRARY) / CATALOG)
