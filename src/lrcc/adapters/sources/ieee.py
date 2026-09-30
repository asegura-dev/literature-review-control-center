"""IEEE Xplore, through its Metadata Search API (ADR-0015).

The key travels as the ``apikey`` query parameter, so it is always passed as a secret parameter:
sent, and recorded only as ``[redacted]``. The API answers with JSON, up to 200 records a call.
The free key allows 200 calls a day. A refusal is not retried, since a retry would spend calls.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.safe_json import items, mapping, parse_json, text
from lrcc.domain.errors import SourceError
from lrcc.domain.gold import GoldWork
from lrcc.domain.record import Record, SearchResult
from lrcc.domain.secrets import NO_SECRETS, Secrets

API = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
#: Records requested per call; the API's maximum.
PAGE = 200

_YEAR = re.compile(r"\d{4}")


class IeeeSource:
    """The IEEE Xplore implementation of the source port."""

    name = "ieee"

    def __init__(self, client: HttpClient, secrets: Secrets = NO_SECRETS) -> None:
        """Create the source.

        Args:
            client: The program's HTTP client.
            secrets: The keys of this run. ``IEEE_API_KEY`` is required when a request is made,
                not before, so a replay needs no key.
        """
        self._client = client
        self._secrets = secrets

    def _key(self) -> dict[str, str]:
        return {"apikey": self._secrets.require("IEEE_API_KEY", "IEEE Xplore")}

    def search(self, query: str, limit: int) -> SearchResult:
        """Run ``query`` on IEEE Xplore and return at most ``limit`` records.

        Args:
            query: The search string, in IEEE Xplore's Boolean syntax.
            limit: The most records to retrieve.

        Returns:
            The count IEEE Xplore reported, the records retrieved, and the raw answers.

        Raises:
            ConfigError: If ``IEEE_API_KEY`` is not set.
            NetworkError: If a request is refused or fails.
            SourceError: If an answer cannot be read.
        """
        responses = []
        retrieved = 0
        reported: int | None = None
        while True:
            page = self._client.fetch(
                API,
                {
                    "querytext": query,
                    "format": "json",
                    "max_records": str(min(PAGE, limit - retrieved)),
                    "start_record": str(retrieved + 1),
                },
                secret_params=self._key(),
            )
            responses.append(page)
            count, articles = _page(page.body)
            # The count is the one the source reported when the search began: a later page
            # may report something else, and the last one sometimes reports nothing at all.
            reported = count if reported is None else reported
            retrieved += len(articles)
            if not articles or retrieved >= min(limit, reported):
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

        Args:
            bodies: The pages as received, in the order they were asked for.

        Returns:
            The records, in the order IEEE Xplore gave them.

        Raises:
            SourceError: If a page cannot be read.
        """
        return tuple(_record(article) for body in bodies for article in _page(body)[1])

    def holds(self, work: GoldWork, query: str | None) -> bool | None:
        """Say whether IEEE Xplore holds ``work``, and whether ``query`` retrieves it.

        The work is looked up by its DOI. With a query, the string and the DOI are sent
        together, and the API returns the records that satisfy both.

        Args:
            work: A work from a gold set.
            query: A search string, or None to ask only whether IEEE Xplore holds the work.

        Returns:
            True or False, or None if the work has no DOI.

        Raises:
            ConfigError: If ``IEEE_API_KEY`` is not set.
            NetworkError: If the request is refused or fails.
            SourceError: If the answer cannot be read.
        """
        if not work.doi:
            return None
        params = {"doi": work.doi, "format": "json", "max_records": "1"}
        if query is not None:
            params["querytext"] = query
        reported, _ = _page(self._client.get(API, params, secret_params=self._key()))
        return reported > 0


def _page(body: bytes) -> tuple[int, list[dict[str, object]]]:
    document = mapping(parse_json(body, "IEEE Xplore"))
    count = text(document.get("total_records"))
    if not count.isdigit():
        raise SourceError("IEEE Xplore answered without a count")
    return int(count), [mapping(article) for article in items(document.get("articles"))]


def _record(article: dict[str, object]) -> Record:
    number = text(article.get("article_number"))
    if not number:
        raise SourceError("IEEE Xplore answered with an article that has no article number")
    names = (text(author.get("full_name")) for author in map(mapping, _authors(article)))
    year = _YEAR.search(text(article.get("publication_year")))
    return Record(
        source=IeeeSource.name,
        source_id=number,
        title=text(article.get("title")),
        authors=tuple(name for name in names if name),
        year=int(year.group()) if year else None,
        doi=text(article.get("doi")).lower() or None,
        abstract=text(article.get("abstract")) or None,
    )


def _authors(article: dict[str, object]) -> list[object]:
    return items(mapping(article.get("authors")).get("authors"))
