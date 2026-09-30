"""``check-query``: a search string tested against a gold set, source by source (ADR-0014).

Each gold work gets one of four states, and only "missed" is the string's fault. The answers of
PubMed and arXiv are synthetic and built inline: each test says which identifiers the source
holds and which ones the string retrieves.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner, Result

from lrcc.adapters.http import HttpClient
from lrcc.adapters.sources.arxiv import API, ArxivSource
from lrcc.adapters.sources.pubmed import ESEARCH, PubMedSource
from lrcc.domain.config import HostConfig, NetworkConfig
from lrcc.domain.errors import ReviewError
from lrcc.domain.gold import GoldWork, parse_gold_set
from lrcc.views.cli.app import app

runner = CliRunner()

NETWORK = NetworkConfig(
    enabled=True,
    hosts={
        "eutils.ncbi.nlm.nih.gov": HostConfig(min_interval=0),
        "export.arxiv.org": HostConfig(min_interval=0),
    },
)

GOLD = {
    "format": 1,
    "works": [
        {"label": "Found", "doi": "https://doi.org/10.0000/Synthetic.FOUND"},
        {"label": "Missed", "pmid": 90000002},
        {"label": "Elsewhere", "doi": "10.0000/synthetic.elsewhere"},
        {"label": "Preprint", "arxiv": "arXiv:9912.00001v2", "note": "only on arXiv"},
        {"label": "Nameless"},
    ],
}


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


def _count(value: int) -> httpx.Response:
    return httpx.Response(
        200, content=f"<eSearchResult><Count>{value}</Count></eSearchResult>".encode()
    )


def pubmed_answers(
    indexed: set[str], retrieved: set[str]
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer ``esearch`` as PubMed would, holding ``indexed`` while the string finds ``retrieved``.

    A term holding the protocol's string (``AND``) is a retrieval question; any other is an
    indexing question.
    """

    def answer(request: httpx.Request) -> httpx.Response:
        term = parse_qs(request.url.query.decode())["term"][0]
        pool = retrieved if " AND (" in term else indexed
        return _count(1 if any(key in term for key in pool) else 0)

    return answer


def arxiv_answers(
    indexed: set[str], retrieved: set[str]
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer the arXiv API as it would, given ``id_list`` with or without ``search_query``."""

    def answer(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.url.query.decode())
        identifier = params["id_list"][0]
        pool = retrieved if "search_query" in params else indexed
        entry = (
            f"<entry><id>http://arxiv.org/abs/{identifier}v1</id><title>t</title></entry>"
            if identifier in pool
            else ""
        )
        feed = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            '<opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
            f"{1 if entry else 0}</opensearch:totalResults>{entry}</feed>"
        )
        return httpx.Response(200, content=feed.encode())

    return answer


# --- the gold set file


def test_identifiers_are_normalised() -> None:
    """DOIs lose their resolver and case, arXiv ids their prefix and version, PMIDs become text."""
    gold = parse_gold_set(yaml.safe_dump(GOLD).encode(), source="gold.yaml")
    found, missed, _, preprint, nameless = gold.works
    assert found.doi == "10.0000/synthetic.found"
    assert missed.pmid == "90000002"
    assert preprint.arxiv == "9912.00001"
    assert nameless.identifiers == "no identifier"


@pytest.mark.parametrize(
    ("work", "expected"),
    [
        ({"label": "x", "doi": "not-a-doi"}, "works.0.doi: must be a DOI"),
        ({"label": "x", "pmid": "12a"}, "works.0.pmid: must be a PMID"),
        ({"label": "x", "arxiv": "abc"}, "works.0.arxiv: must be an arXiv identifier"),
        ({"label": ""}, "works.0.label: must not be empty"),
    ],
)
def test_a_malformed_identifier_is_named(work: dict[str, object], expected: str) -> None:
    """A typo in an identifier would quietly turn a gold work into a false miss."""
    with pytest.raises(ReviewError) as caught:
        parse_gold_set(yaml.safe_dump({"format": 1, "works": [work]}).encode(), source="g")
    (detail,) = caught.value.details
    assert detail.startswith(expected)


def test_an_unquoted_arxiv_identifier_is_refused_not_repaired() -> None:
    """YAML reads 2508.02100 as the number 2508.021; guessing the zeros back would be a lie."""
    text = b"format: 1\nworks:\n  - label: x\n    arxiv: 2508.02100\n"
    with pytest.raises(ReviewError) as caught:
        parse_gold_set(text, source="gold.yaml")
    (detail,) = caught.value.details
    assert detail.startswith("works.0.arxiv: write the arXiv identifier in quotes")


def test_labels_are_unique() -> None:
    """Two works with one label could not be told apart in a report."""
    works = [{"label": "Same", "doi": "10.0000/a"}, {"label": "Same", "doi": "10.0000/b"}]
    with pytest.raises(ReviewError) as caught:
        parse_gold_set(yaml.safe_dump({"format": 1, "works": works}).encode(), source="g")
    assert "works: labels must be unique; repeated: Same" in caught.value.details


# --- the sources


def test_pubmed_asks_by_doi_or_pmid(respx_mock: respx.MockRouter) -> None:
    """One count-only request per question; the string and the identifier are joined by AND."""
    route = respx_mock.get(ESEARCH).mock(side_effect=pubmed_answers({"90000002"}, set()))
    source = PubMedSource(HttpClient(NETWORK))
    work = GoldWork(label="w", doi="10.0000/x", pmid="90000002")
    assert source.holds(work, None) is True
    assert source.holds(work, "a AND b") is False
    terms = [parse_qs(call.request.url.query.decode())["term"][0] for call in route.calls]
    assert terms == [
        '("10.0000/x"[doi] OR 90000002[pmid])',
        '(a AND b) AND ("10.0000/x"[doi] OR 90000002[pmid])',
    ]
    assert parse_qs(route.calls.last.request.url.query.decode())["retmax"] == ["0"]


def test_arxiv_needs_an_arxiv_identifier(respx_mock: respx.MockRouter) -> None:
    """A work known only by DOI cannot be checked on arXiv, which cannot be searched by DOI."""
    source = ArxivSource(HttpClient(NETWORK))
    assert source.holds(GoldWork(label="w", doi="10.0000/x"), None) is None
    assert respx_mock.calls.call_count == 0


# --- the command


@pytest.fixture
def review(make_config: Callable[..., Path], workspace_root: Path) -> str:
    """The review ``example``, with the gold set above, and a configuration allowing both hosts."""
    network = {
        "enabled": True,
        "hosts": {
            "eutils.ncbi.nlm.nih.gov": {"min_interval": 0},
            "export.arxiv.org": {"min_interval": 0},
        },
    }
    config = str(make_config(workspace_root, network=network))
    lrcc("init", "example", "--config", config)
    gold = workspace_root / "reviews" / "example" / "gold.yaml"
    gold.write_text(yaml.safe_dump(GOLD), encoding="utf-8")
    return config


def test_each_state_is_counted_and_named(review: str, respx_mock: respx.MockRouter) -> None:
    """Retrieved, missed, not indexed and unknown are told apart, and a miss exits 1."""
    respx_mock.get(ESEARCH).mock(
        side_effect=pubmed_answers(
            indexed={"10.0000/synthetic.found", "90000002"},
            retrieved={"10.0000/synthetic.found"},
        )
    )
    result = lrcc("check-query", "example", "--source", "pubmed", "--config", review)
    assert result.exit_code == 1
    assert "  1  retrieved" in result.stdout
    assert "  1  missed" in result.stdout
    assert "  1  not indexed" in result.stdout
    assert "  2  unknown" in result.stdout
    assert "  - Missed  (pmid:90000002)" in result.stdout
    assert "The string misses gold works this source holds" in result.stdout


def test_a_string_that_finds_everything_indexed_passes(
    review: str, respx_mock: respx.MockRouter
) -> None:
    """Works a source does not hold are coverage, not a failure of the string."""
    respx_mock.get(API).mock(side_effect=arxiv_answers({"9912.00001"}, {"9912.00001"}))
    result = lrcc("check-query", "example", "--source", "arxiv", "--config", review, "--json")
    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["complete"] is True
    assert data["counts"] == {"retrieved": 1, "missed": 0, "not indexed": 0, "unknown": 4}


def test_a_review_without_a_gold_set(
    make_config: Callable[..., Path], workspace_root: Path, respx_mock: respx.MockRouter
) -> None:
    """The file is named, and nothing is requested."""
    config = str(make_config(workspace_root, network={"enabled": True, "hosts": {}}))
    lrcc("init", "example", "--config", config)
    result = lrcc("check-query", "example", "--source", "pubmed", "--config", config)
    assert result.exit_code == 1
    assert "has no gold set" in result.stderr
    assert respx_mock.calls.call_count == 0


def test_an_empty_gold_set_is_named() -> None:
    """A gold set with no works checks nothing, so it is an error."""
    with pytest.raises(ReviewError) as caught:
        parse_gold_set(b"format: 1\nworks: []\n", source="gold.yaml")
    assert caught.value.details == ("works: must list at least one work",)
