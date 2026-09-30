"""Composition: the one place the view builds adapters from the configuration (ADR-0003).

The view is the driving adapter, so constructing the HTTP client and a source, and handing them
to a feature, is its job. No other view module may import ``adapters``.
"""

from __future__ import annotations

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.arxiv import ArxivSource
from lrcc.adapters.sources.pubmed import PubMedSource
from lrcc.domain.config import Config

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
