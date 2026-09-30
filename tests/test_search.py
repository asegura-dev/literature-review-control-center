"""``lrcc search`` driven as a person drives it, against a mocked transport (ADR-0011).

The command builds the real HTTP client and the real source from the configuration file, so
these tests cover the whole path but the wire. No route is mocked unless a test expects a
request, which makes "nothing was requested" an assertion and not an assumption.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner, Result

from lrcc.adapters.sources.arxiv import API
from lrcc.adapters.sources.pubmed import EFETCH, ESEARCH
from lrcc.views.cli.app import SourceName, app
from lrcc.views.cli.composition import SOURCE_NAMES

runner = CliRunner()

ALLOWED = {
    "enabled": True,
    "hosts": {
        "eutils.ncbi.nlm.nih.gov": {"min_interval": 0},
        "export.arxiv.org": {"min_interval": 0},
    },
}


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def review(make_config: Callable[..., Path], workspace_root: Path) -> Callable[..., str]:
    """Create the review ``example`` and return a function giving a config path for a network."""
    lrcc("init", "example", "--config", str(make_config(workspace_root)))

    def config(**network: object) -> str:
        return str(make_config(workspace_root, network=network or ALLOWED))

    return config


def test_search_prints_the_count_and_the_records(
    review: Callable[..., str],
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """The reported count, the records, and the reminder that nothing was stored."""
    respx_mock.get(API).mock(
        return_value=httpx.Response(200, content=fixture_bytes("arxiv_feed.xml"))
    )
    result = lrcc("search", "example", "--source", "arxiv", "--config", review())
    assert result.exit_code == 0, result.stderr
    assert "arxiv reports 57 records" in result.stdout
    assert "2 retrieved" in result.stdout
    assert "9912.00001" in result.stdout
    assert "Ada Example" in result.stdout
    assert "Nothing was stored" in result.stdout


def test_search_sends_the_string_the_protocol_holds(
    review: Callable[..., str],
    workspace_root: Path,
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """The query is the protocol's, whole, and the outcome names the protocol's digest."""
    esearch = respx_mock.get(ESEARCH).mock(
        return_value=httpx.Response(200, content=fixture_bytes("pubmed_esearch.xml"))
    )
    respx_mock.get(EFETCH).mock(
        return_value=httpx.Response(200, content=fixture_bytes("pubmed_efetch.xml"))
    )
    config = review()
    result = lrcc("search", "example", "--source", "pubmed", "--limit", "2", "--config", config)
    assert result.exit_code == 0, result.stderr

    protocol = yaml.safe_load(
        (workspace_root / "reviews" / "example" / "protocol.yaml").read_text(encoding="utf-8")
    )
    assert esearch.calls.last.request.url.params["term"] == protocol["sources"]["pubmed"]["query"]
    assert esearch.calls.last.request.url.params["retmax"] == "2"

    data = json.loads(
        lrcc("search", "example", "--source", "pubmed", "--config", config, "--json").stdout
    )
    checked = json.loads(lrcc("validate", "example", "--config", config, "--json").stdout)
    assert data["protocol_sha256"] == checked["sha256"]
    assert data["reported"] == 3
    assert data["retrieved"] == 2
    assert data["stored"] is False
    assert data["records"][0]["source_id"] == "90000001"
    assert data["records"][0]["authors"] == ["Example, Ada", "Synthetic Fixture Group"]


def test_with_the_network_off_nothing_is_requested(
    config_file: Path, respx_mock: respx.MockRouter
) -> None:
    """The default: a configuration without a network section cannot search."""
    lrcc("init", "example", "--config", str(config_file))
    result = lrcc("search", "example", "--source", "arxiv", "--config", str(config_file))
    assert result.exit_code == 1
    assert "the network is off" in result.stderr
    assert "network.enabled" in result.stderr
    assert respx_mock.calls.call_count == 0


def test_a_host_that_is_not_listed_is_not_contacted(
    review: Callable[..., str], respx_mock: respx.MockRouter
) -> None:
    """Turning the network on allows only the hosts that are named."""
    config = review(enabled=True, hosts={"eutils.ncbi.nlm.nih.gov": {"min_interval": 0}})
    result = lrcc("search", "example", "--source", "arxiv", "--config", config)
    assert result.exit_code == 1
    assert "export.arxiv.org is not an allowed host" in result.stderr
    assert respx_mock.calls.call_count == 0


def test_a_protocol_without_a_string_for_the_source(
    review: Callable[..., str], workspace_root: Path, respx_mock: respx.MockRouter
) -> None:
    """Asking for a source the protocol does not search says which ones it does."""
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    del data["sources"]["arxiv"]
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lrcc("search", "example", "--source", "arxiv", "--config", review())
    assert result.exit_code == 1
    assert "has no search string for arxiv" in result.stderr
    assert "its sources are: pubmed" in result.stderr
    assert respx_mock.calls.call_count == 0


def test_a_source_error_is_reported_as_data_with_json(
    review: Callable[..., str],
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """A rejected query reaches a script as JSON, with exit code 1."""
    respx_mock.get(API).mock(
        return_value=httpx.Response(200, content=fixture_bytes("arxiv_error.xml"))
    )
    result = lrcc("search", "example", "--source", "arxiv", "--config", review(), "--json")
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "arXiv rejected the query"


def test_an_unknown_source_is_a_usage_error(review: Callable[..., str]) -> None:
    """Only sources with an adapter are offered."""
    result = lrcc("search", "example", "--source", "scopus", "--config", review())
    assert result.exit_code == 2


def test_the_command_offers_exactly_the_sources_that_exist() -> None:
    """The choices of ``--source`` and the adapters composition can build never drift apart."""
    assert tuple(sorted(name.value for name in SourceName)) == SOURCE_NAMES
