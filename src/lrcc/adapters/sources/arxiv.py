"""arXiv, through its Atom API (ADR-0011).

Each request returns the count arXiv reports and a page of entries. arXiv reports a bad query as
a feed holding a single "Error" entry, with HTTP 200, so that case is recognised and raised.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.safe_xml import clean, full_text, parse_xml
from lrcc.domain.errors import SourceError
from lrcc.domain.record import Record, SearchResult

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

API = "https://export.arxiv.org/api/query"
#: Entries requested per call. A run pages until it has every entry arXiv reports.
PAGE = 100
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

#: ``http://arxiv.org/abs/2401.00001v2`` names the paper ``2401.00001``; the suffix is a version.
_IDENTIFIER = re.compile(r"arxiv\.org/abs/(?P<id>.+?)(?:v\d+)?$")


class ArxivSource:
    """The arXiv implementation of the source port."""

    name = "arxiv"

    def __init__(self, client: HttpClient) -> None:
        """Create the source.

        Args:
            client: The program's HTTP client.
        """
        self._client = client

    def search(self, query: str, limit: int) -> SearchResult:
        """Run ``query`` on arXiv and return at most ``limit`` records.

        Args:
            query: The search string, in arXiv API syntax.
            limit: The most records to retrieve.

        Returns:
            The count arXiv reported, the records retrieved, and the raw answers.

        Raises:
            NetworkError: If the request is refused or fails.
            SourceError: If the answer cannot be read, or arXiv rejects the query.
        """
        responses = []
        retrieved = 0
        while True:
            page = self._client.fetch(
                API,
                {
                    "search_query": query,
                    "start": str(retrieved),
                    "max_results": str(min(PAGE, limit - retrieved)),
                },
            )
            responses.append(page)
            reported, entries = _page(page.body)
            retrieved += len(entries)
            # An empty page ends the loop even if arXiv reported more than it delivers.
            if not entries or retrieved >= min(limit, reported):
                break
        return SearchResult(
            source=self.name,
            query=query,
            reported=reported,
            records=self.records_from([response.body for response in responses]),
            responses=tuple(responses),
        )

    def records_from(self, bodies: Sequence[bytes]) -> tuple[Record, ...]:
        """Derive the records from the raw answers of one search, in order.

        A search and a replay both derive their records here, so they cannot disagree.

        Args:
            bodies: The pages as received, in the order they were asked for.

        Returns:
            The records, in the order arXiv gave them.

        Raises:
            SourceError: If a page cannot be read.
        """
        return tuple(_record(entry) for body in bodies for entry in _page(body)[1])


def _page(body: bytes) -> tuple[int, list[Element]]:
    feed = parse_xml(body, "arXiv")
    entries = feed.findall("atom:entry", NAMESPACES)
    for entry in entries:
        if "/api/errors" in clean(entry.findtext("atom:id", namespaces=NAMESPACES)):
            raise SourceError(
                "arXiv rejected the query",
                [full_text(entry.find("atom:summary", NAMESPACES)) or "no detail"],
            )
    count = clean(feed.findtext("opensearch:totalResults", namespaces=NAMESPACES))
    if not count.isdigit():
        raise SourceError("arXiv answered without a count")
    return int(count), entries


def _record(entry: Element) -> Record:
    match = _IDENTIFIER.search(clean(entry.findtext("atom:id", namespaces=NAMESPACES)))
    if match is None:
        raise SourceError("arXiv answered with an entry that has no arXiv identifier")
    published = clean(entry.findtext("atom:published", namespaces=NAMESPACES))
    doi = clean(entry.findtext("arxiv:doi", namespaces=NAMESPACES)).lower()
    names = (clean(node.text) for node in entry.findall("atom:author/atom:name", NAMESPACES))
    return Record(
        source=ArxivSource.name,
        source_id=match.group("id"),
        title=full_text(entry.find("atom:title", NAMESPACES)),
        authors=tuple(name for name in names if name),
        year=int(published[:4]) if published[:4].isdigit() else None,
        doi=doi or None,
        abstract=full_text(entry.find("atom:summary", NAMESPACES)) or None,
    )
