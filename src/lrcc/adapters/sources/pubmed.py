"""PubMed, through NCBI's E-utilities (ADR-0011).

A search is two steps: ``esearch`` returns the count PubMed reports and the identifiers, and
``efetch`` returns the records for those identifiers, requested in batches.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.safe_xml import clean, full_text, parse_xml
from lrcc.domain.errors import SourceError
from lrcc.domain.record import Record, SearchResult

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#: NCBI asks tools to name themselves in every request.
TOOL = "lrcc"
#: The most identifiers one ``esearch`` call returns. Beyond it, NCBI requires its history server.
ESEARCH_MAX = 10_000
#: Identifiers requested per ``efetch`` call.
BATCH = 200

_YEAR = re.compile(r"\d{4}")


class PubMedSource:
    """The PubMed implementation of the source port."""

    name = "pubmed"

    def __init__(self, client: HttpClient) -> None:
        """Create the source.

        Args:
            client: The program's HTTP client.
        """
        self._client = client

    def search(self, query: str, limit: int) -> SearchResult:
        """Run ``query`` on PubMed and return at most ``limit`` records.

        Args:
            query: The search string, in PubMed syntax.
            limit: The most records to retrieve.

        Returns:
            The count PubMed reported, and the records retrieved.

        Raises:
            NetworkError: If a request is refused or fails.
            SourceError: If an answer cannot be read.
        """
        searched = self._client.fetch(
            ESEARCH,
            {
                "db": "pubmed",
                "term": query,
                "retmax": str(min(limit, ESEARCH_MAX)),
                "retmode": "xml",
                "tool": TOOL,
            },
        )
        responses = [searched]
        found = parse_xml(searched.body, "PubMed")
        count = clean(found.findtext("./Count"))
        if not count.isdigit():
            raise SourceError(
                "PubMed answered without a count",
                [clean(found.findtext(".//ERROR")) or "no detail"],
            )
        identifiers = [clean(node.text) for node in found.findall("./IdList/Id")]
        records: list[Record] = []
        for start in range(0, len(identifiers), BATCH):
            batch = identifiers[start : start + BATCH]
            fetched = self._client.fetch(
                EFETCH, {"db": "pubmed", "id": ",".join(batch), "retmode": "xml", "tool": TOOL}
            )
            responses.append(fetched)
            articles = parse_xml(fetched.body, "PubMed").findall("./PubmedArticle")
            records.extend(_record(article) for article in articles)
        return SearchResult(
            source=self.name,
            query=query,
            reported=int(count),
            records=tuple(records),
            responses=tuple(responses),
        )


def _record(article: Element) -> Record:
    identifier = clean(article.findtext("./MedlineCitation/PMID"))
    details = article.find("./MedlineCitation/Article")
    if not identifier or details is None:
        raise SourceError("PubMed answered with an article that has no PMID or no details")
    authors = []
    for author in details.findall("./AuthorList/Author"):
        last = clean(author.findtext("LastName"))
        fore = clean(author.findtext("ForeName"))
        name = (
            f"{last}, {fore}" if last and fore else last or clean(author.findtext("CollectiveName"))
        )
        if name:
            authors.append(name)
    date = details.find("./Journal/JournalIssue/PubDate")
    year = _YEAR.search(full_text(date))
    abstract = " ".join(full_text(part) for part in details.findall("./Abstract/AbstractText"))
    return Record(
        source=PubMedSource.name,
        source_id=identifier,
        title=full_text(details.find("ArticleTitle")),
        authors=tuple(authors),
        year=int(year.group()) if year else None,
        doi=_doi(article, details),
        abstract=abstract or None,
    )


def _doi(article: Element, details: Element) -> str | None:
    candidates = [
        node
        for node in article.findall("./PubmedData/ArticleIdList/ArticleId")
        if node.get("IdType") == "doi"
    ] + [node for node in details.findall("ELocationID") if node.get("EIdType") == "doi"]
    for node in candidates:
        value = clean(node.text).lower()
        if value:
            return value
    return None
