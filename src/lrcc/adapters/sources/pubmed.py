"""PubMed, through NCBI's E-utilities (ADR-0011).

A search is two steps: ``esearch`` returns the count PubMed reports and the identifiers, and
``efetch`` returns the records for those identifiers, requested in batches.

``efetch`` answers with two kinds of record: ``PubmedArticle`` for journal articles, and
``PubmedBookArticle`` for books and book chapters. Both are read. The first real run reported
2,499 records and retrieved 2,489, because only the first kind was read; the ten missing were
book records (ADR-0013).
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
            The count PubMed reported, the records retrieved, and the raw answers.

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
        for start in range(0, len(identifiers), BATCH):
            batch = identifiers[start : start + BATCH]
            responses.append(
                self._client.fetch(
                    EFETCH, {"db": "pubmed", "id": ",".join(batch), "retmode": "xml", "tool": TOOL}
                )
            )
        return SearchResult(
            source=self.name,
            query=query,
            reported=int(count),
            records=self.records_from([response.body for response in responses]),
            responses=tuple(responses),
        )

    def records_from(self, bodies: Sequence[bytes]) -> tuple[Record, ...]:
        """Derive the records from the raw answers of one search, in order.

        A search and a replay both derive their records here, so they cannot disagree.

        Args:
            bodies: The answers as received: the ``esearch`` answer first, then each ``efetch``.

        Returns:
            The records, in the order PubMed gave them.

        Raises:
            SourceError: If an answer cannot be read.
        """
        records = []
        for body in bodies[1:]:
            for node in parse_xml(body, "PubMed"):
                if node.tag == "PubmedArticle":
                    records.append(_article(node))
                elif node.tag == "PubmedBookArticle":
                    records.append(_book(node))
        return tuple(records)


def _authors(parent: Element | None) -> tuple[str, ...]:
    authors = []
    for author in parent.findall("./AuthorList/Author") if parent is not None else []:
        last = clean(author.findtext("LastName"))
        fore = clean(author.findtext("ForeName"))
        name = (
            f"{last}, {fore}" if last and fore else last or clean(author.findtext("CollectiveName"))
        )
        if name:
            authors.append(name)
    return tuple(authors)


def _year(date: Element | None) -> int | None:
    match = _YEAR.search(full_text(date))
    return int(match.group()) if match else None


def _abstract(parent: Element) -> str | None:
    text = " ".join(full_text(part) for part in parent.findall("./Abstract/AbstractText"))
    return text or None


def _doi(*candidates: Element) -> str | None:
    for node in candidates:
        value = clean(node.text).lower()
        if value:
            return value
    return None


def _article(article: Element) -> Record:
    identifier = clean(article.findtext("./MedlineCitation/PMID"))
    details = article.find("./MedlineCitation/Article")
    if not identifier or details is None:
        raise SourceError("PubMed answered with an article that has no PMID or no details")
    return Record(
        source=PubMedSource.name,
        source_id=identifier,
        title=full_text(details.find("ArticleTitle")),
        authors=_authors(details),
        year=_year(details.find("./Journal/JournalIssue/PubDate")),
        doi=_doi(
            *(
                node
                for node in article.findall("./PubmedData/ArticleIdList/ArticleId")
                if node.get("IdType") == "doi"
            ),
            *(node for node in details.findall("ELocationID") if node.get("EIdType") == "doi"),
        ),
        abstract=_abstract(details),
    )


def _book(article: Element) -> Record:
    """Read a book or a book chapter.

    A chapter carries its own ``ArticleTitle`` and authors. A record for a whole book has
    neither, so the book's title and authors are used.
    """
    document = article.find("./BookDocument")
    identifier = clean(document.findtext("PMID")) if document is not None else ""
    if document is None or not identifier:
        raise SourceError("PubMed answered with a book record that has no PMID")
    book = document.find("Book")
    chapter_title = full_text(document.find("ArticleTitle"))
    book_title = full_text(book.find("BookTitle")) if book is not None else ""
    return Record(
        source=PubMedSource.name,
        source_id=identifier,
        title=chapter_title or book_title,
        authors=_authors(document) or _authors(book),
        year=_year(book.find("PubDate") if book is not None else None),
        doi=_doi(*(node for node in article.iter("ArticleId") if node.get("IdType") == "doi")),
        abstract=_abstract(document),
    )
