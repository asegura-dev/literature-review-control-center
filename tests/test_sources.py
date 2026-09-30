"""PubMed and arXiv, parsed from synthetic fixtures through the real HTTP client (ADR-0011).

The fixtures under ``tests/fixtures`` were written by hand and hold no content from either
source. ``respx`` answers in the sources' place, so these tests run offline.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.arxiv import API, ArxivSource
from lrcc.adapters.sources.pubmed import BATCH, EFETCH, ESEARCH, PubMedSource
from lrcc.domain.config import HostConfig, NetworkConfig
from lrcc.domain.errors import SourceError
from lrcc.domain.record import Record

NETWORK = NetworkConfig(
    enabled=True,
    hosts={
        "eutils.ncbi.nlm.nih.gov": HostConfig(min_interval=0),
        "export.arxiv.org": HostConfig(min_interval=0),
    },
)

#: An XML document that declares an entity: the opening move of an entity-expansion attack.
WITH_ENTITIES = (
    b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaaaaaaaa">]><feed>&a;&a;&a;</feed>'
)


def _ok(content: bytes) -> httpx.Response:
    return httpx.Response(200, content=content)


def test_pubmed_records(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Two steps, esearch then efetch, become the reported count and uniform records."""
    esearch = respx_mock.get(ESEARCH).mock(return_value=_ok(fixture_bytes("pubmed_esearch.xml")))
    efetch = respx_mock.get(EFETCH).mock(return_value=_ok(fixture_bytes("pubmed_efetch.xml")))
    result = PubMedSource(HttpClient(NETWORK)).search("a AND b", limit=2)

    assert esearch.calls.last.request.url.params["term"] == "a AND b"
    assert esearch.calls.last.request.url.params["retmax"] == "2"
    assert efetch.calls.last.request.url.params["id"] == "90000001,90000002"
    assert result.reported == 3
    assert result.records == (
        Record(
            source="pubmed",
            source_id="90000001",
            title="A synthetic title with inline markup broken over two lines.",
            authors=("Example, Ada", "Synthetic Fixture Group"),
            year=2021,
            doi="10.0000/synthetic.1",
            abstract="An invented background sentence. An invented results sentence.",
        ),
        Record(
            source="pubmed",
            source_id="90000002",
            title="A second synthetic title, without an abstract.",
            authors=("Sample, Grace",),
            year=2019,
            doi="10.0000/synthetic.2",
            abstract=None,
        ),
    )


def test_pubmed_fetches_in_batches(respx_mock: respx.MockRouter) -> None:
    """More identifiers than one batch holds are fetched in several requests."""
    identifiers = "".join(f"<Id>{90000000 + n}</Id>" for n in range(BATCH + 1))
    found = f"<eSearchResult><Count>999</Count><IdList>{identifiers}</IdList></eSearchResult>"
    respx_mock.get(ESEARCH).mock(return_value=_ok(found.encode()))
    efetch = respx_mock.get(EFETCH).mock(return_value=_ok(b"<PubmedArticleSet/>"))
    result = PubMedSource(HttpClient(NETWORK)).search("a", limit=BATCH + 1)
    assert efetch.call_count == 2
    assert result.reported == 999
    assert result.records == ()


def test_pubmed_without_a_count_is_an_error(respx_mock: respx.MockRouter) -> None:
    """An answer LRCC cannot count is reported, with PubMed's own message when it gives one."""
    respx_mock.get(ESEARCH).mock(
        return_value=_ok(b"<eSearchResult><ERROR>synthetic failure</ERROR></eSearchResult>")
    )
    with pytest.raises(SourceError, match="PubMed answered without a count") as caught:
        PubMedSource(HttpClient(NETWORK)).search("a", limit=1)
    assert caught.value.details == ("synthetic failure",)


def test_arxiv_records(respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]) -> None:
    """One Atom feed becomes the reported count and uniform records, versions stripped."""
    route = respx_mock.get(API).mock(return_value=_ok(fixture_bytes("arxiv_feed.xml")))
    result = ArxivSource(HttpClient(NETWORK)).search('abs:"a b"', limit=2)

    assert route.calls.last.request.url.params["search_query"] == 'abs:"a b"'
    assert route.calls.last.request.url.params["max_results"] == "2"
    assert result.reported == 57
    assert result.records == (
        Record(
            source="arxiv",
            source_id="9912.00001",
            title="A synthetic preprint title broken over two lines",
            authors=("Ada Example", "Grace Sample"),
            year=2023,
            doi="10.0000/synthetic.3",
            abstract="An invented summary sentence.",
        ),
        Record(
            source="arxiv",
            source_id="9912.00002",
            title="A second synthetic preprint, without a DOI",
            authors=("Alan Specimen",),
            year=2022,
            doi=None,
            abstract="Another invented summary sentence.",
        ),
    )


def test_arxiv_rejecting_a_query_is_an_error(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """A bad query comes back from arXiv as HTTP 200 with an "Error" entry, not a record."""
    respx_mock.get(API).mock(return_value=_ok(fixture_bytes("arxiv_error.xml")))
    with pytest.raises(SourceError, match="arXiv rejected the query") as caught:
        ArxivSource(HttpClient(NETWORK)).search("((", limit=1)
    assert caught.value.details == ("a synthetic description of a malformed query",)


@pytest.mark.parametrize(
    ("body", "expected"),
    [(WITH_ENTITIES, "EntitiesForbidden"), (b"<feed><unclosed></feed>", "ParseError")],
)
def test_xml_that_cannot_be_read_safely_is_refused(
    respx_mock: respx.MockRouter, body: bytes, expected: str
) -> None:
    """An answer is data, never trusted: entity declarations and broken XML are both refused."""
    respx_mock.get(API).mock(return_value=_ok(body))
    with pytest.raises(SourceError, match="cannot be read safely") as caught:
        ArxivSource(HttpClient(NETWORK)).search("a", limit=1)
    assert caught.value.details[0].startswith(expected)


def test_pubmed_reads_books_and_chapters_in_order(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Book records are records too, kept in the order PubMed gave them.

    The first real run reported 2,499 records and retrieved 2,489: the ten missing were
    ``PubmedBookArticle`` elements, which the adapter did not read.
    """
    found = (
        b"<eSearchResult><Count>3</Count><IdList><Id>90000003</Id><Id>90000004</Id>"
        b"<Id>90000005</Id></IdList></eSearchResult>"
    )
    respx_mock.get(ESEARCH).mock(return_value=_ok(found))
    respx_mock.get(EFETCH).mock(return_value=_ok(fixture_bytes("pubmed_efetch_books.xml")))
    result = PubMedSource(HttpClient(NETWORK)).search("a", limit=3)

    assert result.reported == len(result.records) == 3
    chapter, article, book = result.records
    assert chapter == Record(
        source="pubmed",
        source_id="90000003",
        title="A synthetic chapter title.",
        authors=("Chapter, Charles",),
        year=2020,
        doi="10.0000/synthetic.book.1",
        abstract="An invented chapter abstract.",
    )
    assert article.source_id == "90000004"
    assert book == Record(
        source="pubmed",
        source_id="90000005",
        title="A Synthetic Report, Recorded as a Whole Book",
        authors=("Synthetic Agency for Reports",),
        year=2018,
        doi=None,
        abstract=None,
    )


def test_records_are_derived_from_the_raw_answers_alone(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """What a search returns is exactly what its stored answers give back, with no request."""
    respx_mock.get(ESEARCH).mock(return_value=_ok(fixture_bytes("pubmed_esearch.xml")))
    respx_mock.get(EFETCH).mock(return_value=_ok(fixture_bytes("pubmed_efetch.xml")))
    respx_mock.get(API).mock(return_value=_ok(fixture_bytes("arxiv_feed.xml")))
    for source in (PubMedSource(HttpClient(NETWORK)), ArxivSource(HttpClient(NETWORK))):
        result = source.search("a", limit=2)
        requests = respx_mock.calls.call_count
        bodies = [response.body for response in result.responses]
        assert source.records_from(bodies) == result.records
        assert respx_mock.calls.call_count == requests
