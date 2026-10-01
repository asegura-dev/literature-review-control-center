"""IEEE Xplore and Scopus (ADR-0015), against synthetic answers and fake keys.

The last tests store real runs through the command, then read every byte the review holds,
database included, to show that no key was kept anywhere.
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
from lrcc.adapters.sources.ieee import API as IEEE_API
from lrcc.adapters.sources.ieee import IeeeSource
from lrcc.adapters.sources.scopus import API as SCOPUS_API
from lrcc.adapters.sources.scopus import ScopusSource
from lrcc.domain.config import HostConfig, NetworkConfig
from lrcc.domain.errors import ConfigError, NetworkError, SourceError
from lrcc.domain.gold import GoldWork
from lrcc.domain.record import Record
from lrcc.domain.secrets import NO_SECRETS, Secrets
from lrcc.views.cli.app import app

IEEE_KEY = "fake-ieee-key-8c1d4e7a"
SCOPUS_KEY = "fake-scopus-key-2b9f6a3c"
SCOPUS_INST = "fake-insttoken-5e0a7d21"

NETWORK = NetworkConfig(
    enabled=True,
    hosts={
        "ieeexploreapi.ieee.org": HostConfig(min_interval=0),
        "api.elsevier.com": HostConfig(min_interval=0),
    },
)
KEYS = Secrets(
    {"IEEE_API_KEY": IEEE_KEY, "SCOPUS_API_KEY": SCOPUS_KEY, "SCOPUS_INSTTOKEN": SCOPUS_INST}
)

#: What IEEE Xplore answers past the last record.
IEEE_EMPTY = b'{"total_records": 3, "articles": []}'


def _ok(body: bytes) -> httpx.Response:
    return httpx.Response(200, content=body)


def _params(call: respx.models.Call) -> dict[str, list[str]]:
    return parse_qs(call.request.url.query.decode())


# --- IEEE Xplore


def test_ieee_records_and_paging(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """JSON becomes uniform records; the key is sent, and the recorded address redacts it."""
    route = respx_mock.get(IEEE_API).mock(
        side_effect=[_ok(fixture_bytes("ieee_search.json")), _ok(IEEE_EMPTY)]
    )
    result = IeeeSource(HttpClient(NETWORK), KEYS).search("distillation AND MRI", 100)

    assert [_params(call)["start_record"] for call in route.calls] == [["1"], ["3"]]
    assert _params(route.calls[0])["apikey"] == [IEEE_KEY]
    assert _params(route.calls[0])["max_records"] == ["100"]
    assert all(IEEE_KEY not in response.url for response in result.responses)
    assert "apikey=[redacted]" in result.responses[0].url
    assert result.reported == 3
    assert result.records == (
        Record(
            source="ieee",
            source_id="90000001",
            title="A synthetic IEEE title about cross-modal distillation",
            authors=("Ada Example", "Grace Sample"),
            year=2021,
            doi="10.0000/synthetic.ieee.1",
            abstract="An invented abstract.",
        ),
        Record(
            source="ieee",
            source_id="90000002",
            title="A second synthetic IEEE title, without a DOI or an abstract",
            authors=("Alan Specimen",),
            year=2019,
            doi=None,
            abstract=None,
        ),
    )


def test_ieee_without_a_key_asks_for_it_and_requests_nothing(respx_mock: respx.MockRouter) -> None:
    """The missing key is named before any call is spent."""
    with pytest.raises(ConfigError, match="IEEE Xplore needs IEEE_API_KEY"):
        IeeeSource(HttpClient(NETWORK), NO_SECRETS).search("a", 10)
    assert respx_mock.calls.call_count == 0


def test_ieee_quota_refusal_is_not_retried(respx_mock: respx.MockRouter) -> None:
    """A 403 is how the service says the key is invalid or the day's calls are spent."""
    respx_mock.get(IEEE_API).mock(
        return_value=httpx.Response(403, content=b"<h1>Developer Over Rate</h1>")
    )
    with pytest.raises(NetworkError, match="answered HTTP 403") as caught:
        IeeeSource(HttpClient(NETWORK), KEYS).search("a", 10)
    assert caught.value.details == ("<h1>Developer Over Rate</h1>",)
    assert respx_mock.calls.call_count == 1


def test_ieee_gold_checks_by_doi(respx_mock: respx.MockRouter) -> None:
    """Held is asked by DOI alone; retrieved by the DOI with the string."""
    route = respx_mock.get(IEEE_API).mock(
        side_effect=[_ok(b'{"total_records": 1}'), _ok(b'{"total_records": 0}')]
    )
    source = IeeeSource(HttpClient(NETWORK), KEYS)
    work = GoldWork(label="w", doi="10.0000/x")
    assert source.holds(work, None) is True
    assert source.holds(work, "a AND b") is False
    first, second = (_params(call) for call in route.calls)
    assert first["doi"] == ["10.0000/x"] and "querytext" not in first
    assert second["doi"] == ["10.0000/x"] and second["querytext"] == ["a AND b"]
    assert source.holds(GoldWork(label="v", arxiv="9912.00001"), None) is None


# --- Scopus


def test_scopus_records_cursor_and_headers(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """The key and token go in headers; the cursor pages; nothing secret is in the address."""
    route = respx_mock.get(SCOPUS_API).mock(
        side_effect=[
            _ok(fixture_bytes("scopus_search.json")),
            _ok(fixture_bytes("scopus_empty.json")),
        ]
    )
    result = ScopusSource(HttpClient(NETWORK), KEYS).search('TITLE-ABS-KEY("x")', 100)

    first, second = route.calls
    assert first.request.headers["X-ELS-APIKey"] == SCOPUS_KEY
    assert first.request.headers["X-ELS-Insttoken"] == SCOPUS_INST
    assert _params(first)["cursor"] == ["*"] and _params(first)["view"] == ["COMPLETE"]
    assert _params(second)["cursor"] == ["SYNTHETICCURSOR1"]
    assert all(SCOPUS_KEY not in r.url and SCOPUS_INST not in r.url for r in result.responses)
    assert result.reported == 3
    assert result.records[0] == Record(
        source="scopus",
        source_id="2-s2.0-90000000001",
        title="A synthetic Scopus title",
        authors=("Example A.", "Sample G."),
        year=2020,
        doi="10.0000/synthetic.scopus.1",
        abstract="An invented Scopus abstract.",
    )
    assert result.records[1].authors == ("Specimen A.",)
    assert result.records[1].doi is None


def test_scopus_empty_result_is_zero_records(
    respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Scopus reports "nothing found" as an entry with an error field; it is not a record."""
    respx_mock.get(SCOPUS_API).mock(return_value=_ok(fixture_bytes("scopus_empty.json")))
    result = ScopusSource(HttpClient(NETWORK), KEYS).search("x", 10)
    assert (result.reported, result.records) == (0, ())


def test_scopus_refusal_quotes_elsevier(respx_mock: respx.MockRouter) -> None:
    """An institution without access to the COMPLETE view is told so in Elsevier's words."""
    body = (
        b'{"service-error":{"status":{"statusCode":"AUTHORIZATION_ERROR",'
        b'"statusText":"The requestor is not authorized to access the requested view"}}}'
    )
    respx_mock.get(SCOPUS_API).mock(return_value=httpx.Response(401, content=body))
    with pytest.raises(NetworkError, match="answered HTTP 401") as caught:
        ScopusSource(HttpClient(NETWORK), KEYS).search("x", 10)
    assert "not authorized to access the requested view" in caught.value.details[0]


def test_scopus_gold_checks_by_doi_and_pmid(respx_mock: respx.MockRouter) -> None:
    """The identifiers become DOI(...) and PMID(...) fields, joined to the string with AND."""
    route = respx_mock.get(SCOPUS_API).mock(
        return_value=_ok(b'{"search-results": {"opensearch:totalResults": "1"}}')
    )
    source = ScopusSource(HttpClient(NETWORK), KEYS)
    work = GoldWork(label="w", doi="10.0000/x", pmid="90000002")
    assert source.holds(work, "TITLE-ABS-KEY(a)") is True
    params = _params(route.calls.last)
    assert params["query"] == ['(TITLE-ABS-KEY(a)) AND (DOI("10.0000/x") OR PMID(90000002))']
    assert params["view"] == ["STANDARD"]
    assert source.holds(GoldWork(label="v", arxiv="9912.00001"), None) is None


# --- the command: keys reach the sources and nothing that is stored

runner = CliRunner()


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def review(make_config: Callable[..., Path], workspace_root: Path) -> str:
    """A review with IEEE and Scopus strings, and fake keys in the ``.env`` beside its config."""
    hosts = {"ieeexploreapi.ieee.org": {"min_interval": 0}, "api.elsevier.com": {"min_interval": 0}}
    config = make_config(workspace_root, network={"enabled": True, "hosts": hosts})
    (config.parent / ".env").write_text(
        f"IEEE_API_KEY={IEEE_KEY}\nSCOPUS_API_KEY={SCOPUS_KEY}\nSCOPUS_INSTTOKEN={SCOPUS_INST}\n",
        encoding="utf-8",
    )
    lrcc("init", "example", "--config", str(config))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["sources"]["ieee"] = {"query": "distillation AND MRI"}
    data["sources"]["scopus"] = {"query": 'TITLE-ABS-KEY("knowledge distillation")'}
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(config)


def _every_byte(folder: Path) -> bytes:
    return b"".join(path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file())


@pytest.mark.parametrize("source", ["ieee", "scopus"])
def test_no_key_is_kept_anywhere_in_the_review(
    source: str,
    review: str,
    workspace_root: Path,
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """A stored run, its response files and its database hold no key, only the mark of one."""
    respx_mock.get(IEEE_API).mock(
        side_effect=[_ok(fixture_bytes("ieee_search.json")), _ok(IEEE_EMPTY)]
    )
    respx_mock.get(SCOPUS_API).mock(
        side_effect=[
            _ok(fixture_bytes("scopus_search.json")),
            _ok(fixture_bytes("scopus_empty.json")),
        ]
    )
    result = lrcc("search", "example", "--source", source, "--config", review, "--json")
    assert result.exit_code == 0, result.stderr
    run = json.loads(result.stdout)
    assert run["retrieved"] == 2

    stored = _every_byte(workspace_root / "reviews" / "example")
    for key in (IEEE_KEY, SCOPUS_KEY, SCOPUS_INST):
        assert key.encode() not in stored
        assert key not in result.stdout + result.stderr
    if source == "ieee":
        assert "apikey=[redacted]" in run["responses"][0]["url"]


def test_keys_are_read_only_beside_the_configuration(
    review: str, workspace_root: Path, respx_mock: respx.MockRouter
) -> None:
    """A ``.env`` anywhere else, even in the workspace, is not looked at."""
    Path(review).with_name(".env").unlink()
    (workspace_root / ".env").write_text(f"IEEE_API_KEY={IEEE_KEY}\n", encoding="utf-8")
    result = lrcc("search", "example", "--source", "ieee", "--preview", "--config", review)
    assert result.exit_code == 1
    assert "IEEE Xplore needs IEEE_API_KEY" in result.stderr
    assert str(Path(review).with_name(".env")) in result.stderr
    assert respx_mock.calls.call_count == 0


def test_a_replay_needs_no_key(
    review: str,
    workspace_root: Path,
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """Records are rederived from stored answers; the keys can be gone by then."""
    respx_mock.get(IEEE_API).mock(
        side_effect=[_ok(fixture_bytes("ieee_search.json")), _ok(IEEE_EMPTY)]
    )
    assert lrcc("search", "example", "--source", "ieee", "--config", review).exit_code == 0
    Path(review).with_name(".env").unlink()
    respx_mock.reset()
    replayed = lrcc("replay", "example", "--config", review)
    assert replayed.exit_code == 0, replayed.stdout + replayed.stderr
    assert "identical" in replayed.stdout
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize(
    "body", [b"<html>not json</html>", b"[" * 100_000], ids=["html", "deep-nesting"]
)
def test_an_answer_that_is_not_json_is_refused(respx_mock: respx.MockRouter, body: bytes) -> None:
    """Broken or absurdly nested JSON is named as unreadable, never half-read."""
    respx_mock.get(IEEE_API).mock(return_value=_ok(body))
    with pytest.raises(SourceError, match="IEEE Xplore answered with JSON that cannot be read"):
        IeeeSource(HttpClient(NETWORK), KEYS).search("a", 10)
