"""Scopus, through Elsevier's Scopus Search API (ADR-0015).

The key, and the institutional token if there is one, travel as headers, which LRCC never
records. A search asks for the COMPLETE view, because screening needs abstracts, and pages with a
cursor, 25 records a call. Whether the COMPLETE view is granted depends on the institution's
subscription; a refusal quotes Elsevier's explanation.
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

API = "https://api.elsevier.com/content/search/scopus"
#: Records requested per call; the most the COMPLETE view allows.
PAGE = 25
_ACCEPT = {"Accept": "application/json"}
_YEAR = re.compile(r"\d{4}")


class ScopusSource:
    """The Scopus implementation of the source port."""

    name = "scopus"

    def __init__(self, client: HttpClient, secrets: Secrets = NO_SECRETS) -> None:
        """Create the source.

        Args:
            client: The program's HTTP client.
            secrets: The keys of this run. ``SCOPUS_API_KEY`` is required when a request is
                made, not before, so a replay needs no key.
        """
        self._client = client
        self._secrets = secrets

    def _auth(self) -> dict[str, str]:
        headers = {"X-ELS-APIKey": self._secrets.require("SCOPUS_API_KEY", "Scopus")}
        token = self._secrets.get("SCOPUS_INSTTOKEN")
        if token:
            headers["X-ELS-Insttoken"] = token
        return headers

    def search(self, query: str, limit: int) -> SearchResult:
        """Run ``query`` on Scopus and return at most ``limit`` records.

        Args:
            query: The search string, in Scopus advanced-search syntax.
            limit: The most records to retrieve.

        Returns:
            The count Scopus reported, the records retrieved, and the raw answers.

        Raises:
            ConfigError: If ``SCOPUS_API_KEY`` is not set.
            NetworkError: If a request is refused or fails.
            SourceError: If an answer cannot be read.
        """
        responses = []
        retrieved = 0
        reported: int | None = None
        cursor = "*"
        while True:
            page = self._client.fetch(
                API,
                {
                    "query": query,
                    "view": "COMPLETE",
                    "count": str(min(PAGE, limit - retrieved)),
                    "cursor": cursor,
                },
                secret_headers=self._auth(),
                headers=_ACCEPT,
            )
            responses.append(page)
            count, entries, following = _page(page.body)
            # The count is the one the source reported when the search began: a later page
            # may report something else, and the last one sometimes reports nothing at all.
            reported = count if reported is None else reported
            retrieved += len(entries)
            if not entries or retrieved >= min(limit, reported) or following in ("", cursor):
                break
            cursor = following
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
            The records, in the order Scopus gave them.

        Raises:
            SourceError: If a page cannot be read.
        """
        return tuple(_record(entry) for body in bodies for entry in _page(body)[1])

    def holds(self, work: GoldWork, query: str | None) -> bool | None:
        """Say whether Scopus holds ``work``, and whether ``query`` retrieves it.

        The work is found with the ``DOI`` and ``PMID`` fields; with a query, the two are joined
        by ``AND``. One request, asking for a count, in the STANDARD view.

        Args:
            work: A work from a gold set.
            query: A search string, or None to ask only whether Scopus holds the work.

        Returns:
            True or False, or None if the work has neither a DOI nor a PMID.

        Raises:
            ConfigError: If ``SCOPUS_API_KEY`` is not set.
            NetworkError: If the request is refused or fails.
            SourceError: If the answer cannot be read.
        """
        targets = []
        if work.doi:
            targets.append(f'DOI("{work.doi}")')
        if work.pmid:
            targets.append(f"PMID({work.pmid})")
        if not targets:
            return None
        target = " OR ".join(targets)
        term = f"({target})" if query is None else f"({query}) AND ({target})"
        body = self._client.get(
            API,
            {"query": term, "view": "STANDARD", "count": "1"},
            secret_headers=self._auth(),
            headers=_ACCEPT,
        )
        return _page(body)[0] > 0


def _page(body: bytes) -> tuple[int, list[dict[str, object]], str]:
    document = mapping(parse_json(body, "Scopus"))
    results = mapping(document.get("search-results"))
    count = text(results.get("opensearch:totalResults"))
    if not count.isdigit():
        raise SourceError("Scopus answered without a count")
    # An empty result is reported as one entry holding an "error" field, not as no entries.
    entries = [
        mapping(entry) for entry in items(results.get("entry")) if "error" not in mapping(entry)
    ]
    following = text(mapping(results.get("cursor")).get("@next"))
    return int(count), entries, following


def _record(entry: dict[str, object]) -> Record:
    identifier = text(entry.get("eid"))
    if not identifier:
        raise SourceError("Scopus answered with an entry that has no EID")
    names = [text(mapping(author).get("authname")) for author in items(entry.get("author"))]
    authors = tuple(name for name in names if name) or tuple(
        name for name in (text(entry.get("dc:creator")),) if name
    )
    year = _YEAR.search(text(entry.get("prism:coverDate")))
    return Record(
        source=ScopusSource.name,
        source_id=identifier,
        title=text(entry.get("dc:title")),
        authors=authors,
        year=int(year.group()) if year else None,
        doi=text(entry.get("prism:doi")).lower() or None,
        abstract=text(entry.get("dc:description")) or None,
    )
