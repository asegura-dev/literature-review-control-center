"""``lrcc search`` storing runs, and ``lrcc status`` reading them back (ADR-0012).

The commands build the real DuckDB store, the real HTTP client and the real sources; only the
transport is mocked. Every test works in a temporary workspace.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

import duckdb
import httpx
import pytest
import respx
from typer.testing import CliRunner, Result

from lrcc.adapters.sources.arxiv import API
from lrcc.adapters.storage.duckdb_store import DuckDbReviewStore
from lrcc.domain.runs import GENESIS
from lrcc.views.cli.app import app

runner = CliRunner()

NETWORK = {"enabled": True, "hosts": {"export.arxiv.org": {"min_interval": 0}}}

#: A page with no entries: what arXiv returns past the last result.
EMPTY_PAGE = (
    b'<feed xmlns="http://www.w3.org/2005/Atom">'
    b'<opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">57'
    b"</opensearch:totalResults></feed>"
)


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def config(make_config: Callable[..., Path], workspace_root: Path) -> str:
    """The review ``example`` exists, and the configuration allows arXiv."""
    path = str(make_config(workspace_root, network=NETWORK))
    lrcc("init", "example", "--config", path)
    return path


@pytest.fixture
def review_dir(workspace_root: Path) -> Path:
    """The folder of the review ``example``."""
    return workspace_root / "reviews" / "example"


@pytest.fixture
def complete_feed(fixture_bytes: Callable[[str], bytes]) -> bytes:
    """The synthetic feed, reporting exactly the two entries it holds."""
    return fixture_bytes("arxiv_feed.xml").replace(b">57<", b">2<")


def _answer(respx_mock: respx.MockRouter, *bodies: bytes) -> respx.Route:
    return respx_mock.get(API).mock(
        side_effect=[httpx.Response(200, content=body) for body in bodies]
    )


def test_a_run_is_stored_with_its_raw_response(
    config: str, review_dir: Path, respx_mock: respx.MockRouter, complete_feed: bytes
) -> None:
    """The response is on disk byte for byte, and the log holds its digest."""
    _answer(respx_mock, complete_feed)
    result = lrcc("search", "example", "--source", "arxiv", "--config", config, "--json")
    assert result.exit_code == 0, result.stderr
    run = json.loads(result.stdout)

    assert re.fullmatch(r"0001-\d{8}T\d{6}Z-arxiv", run["run_id"])
    assert run["stored"] is True
    assert run["complete"] is True
    assert (run["reported"], run["retrieved"]) == (2, 2)

    (response,) = run["responses"]
    stored = review_dir / "runs" / run["run_id"] / response["file"]
    assert stored.read_bytes() == complete_feed
    assert response["sha256"] == hashlib.sha256(complete_feed).hexdigest()
    assert response["size"] == len(complete_feed)
    assert "search_query=" in response["url"]
    assert (review_dir / "review.duckdb").is_file()


def test_a_run_pages_until_the_source_has_no_more(
    config: str, respx_mock: respx.MockRouter, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Two pages are asked for, both are stored, and the shortfall is said out loud."""
    route = _answer(respx_mock, fixture_bytes("arxiv_feed.xml"), EMPTY_PAGE)
    result = lrcc("search", "example", "--source", "arxiv", "--config", config)
    assert result.exit_code == 0, result.stderr
    assert [call.request.url.params["start"] for call in route.calls] == ["0", "2"]
    assert "2 file(s)" in result.stdout
    assert "Incomplete: arxiv reports 57 records and 2 were retrieved." in result.stdout


def test_runs_are_chained(config: str, review_dir: Path, respx_mock: respx.MockRouter) -> None:
    """The second entry names the first one's hash, and status verifies the chain."""
    feed = EMPTY_PAGE.replace(b">57<", b">0<")
    _answer(respx_mock, feed, feed)
    lrcc("search", "example", "--source", "arxiv", "--config", config)
    lrcc("search", "example", "--source", "arxiv", "--config", config)

    first, second = DuckDbReviewStore(review_dir).log()
    assert first.prev_hash == GENESIS
    assert second.prev_hash == first.entry_hash
    assert second.run.run_id.startswith("0002-")

    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 0, status.stderr
    assert first.run.run_id in status.stdout
    assert second.run.run_id in status.stdout
    assert "The run log verifies" in status.stdout


def test_an_edited_log_is_reported(
    config: str, review_dir: Path, respx_mock: respx.MockRouter, complete_feed: bytes
) -> None:
    """Changing a count directly in the database is caught the next time anyone looks."""
    _answer(respx_mock, complete_feed)
    lrcc("search", "example", "--source", "arxiv", "--config", config)
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute(
        "UPDATE runs SET entry = replace(entry, ?, ?)", ['"reported":2', '"reported":900']
    )
    connection.close()

    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 1
    assert "The run log does not verify" in status.stdout
    assert "its content does not match its hash" in status.stdout

    data = json.loads(lrcc("status", "example", "--config", config, "--json").stdout)
    assert data["chain_intact"] is False


def test_status_says_when_the_protocol_changed_after_a_run(
    config: str, review_dir: Path, respx_mock: respx.MockRouter, complete_feed: bytes
) -> None:
    """A run names the protocol it used; an edit afterwards shows against that run."""
    _answer(respx_mock, complete_feed)
    lrcc("search", "example", "--source", "arxiv", "--config", config)
    assert "current" in lrcc("status", "example", "--config", config).stdout

    protocol = review_dir / "protocol.yaml"
    protocol.write_bytes(protocol.read_bytes() + b"\n# an amendment\n")
    status = lrcc("status", "example", "--config", config, "--json")
    assert json.loads(status.stdout)["runs"][0]["current_protocol"] is False


def test_status_of_a_review_without_runs_creates_nothing(config: str, review_dir: Path) -> None:
    """Asking where a review stands does not write to it."""
    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 0, status.stderr
    assert "No runs are stored yet" in status.stdout
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


def test_a_preview_stores_nothing(
    config: str, review_dir: Path, respx_mock: respx.MockRouter, complete_feed: bytes
) -> None:
    """``--preview`` leaves the review's folder exactly as it was."""
    _answer(respx_mock, complete_feed)
    result = lrcc("search", "example", "--preview", "--source", "arxiv", "--config", config)
    assert result.exit_code == 0, result.stderr
    assert "Nothing was stored" in result.stdout
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


def test_a_failed_search_stores_nothing(
    config: str,
    review_dir: Path,
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """A run exists only if the source answered with records LRCC could read."""
    _answer(respx_mock, fixture_bytes("arxiv_error.xml"))
    result = lrcc("search", "example", "--source", "arxiv", "--config", config)
    assert result.exit_code == 1
    assert "arXiv rejected the query" in result.stderr
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


def test_a_damaged_database_is_an_error_not_a_traceback(config: str, review_dir: Path) -> None:
    """A file that is not a database is named, with the reason DuckDB gives."""
    (review_dir / "review.duckdb").write_bytes(b"this is not a database")
    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 1
    assert "cannot open" in status.stderr


def test_a_log_entry_that_is_not_a_run_is_reported(
    config: str, review_dir: Path, respx_mock: respx.MockRouter, complete_feed: bytes
) -> None:
    """An entry overwritten with something else stops the command with a plain message."""
    _answer(respx_mock, complete_feed)
    lrcc("search", "example", "--source", "arxiv", "--config", config)
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute("UPDATE runs SET entry = ?", ["{}"])
    connection.close()
    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 1
    assert "holds an entry that is not a run" in status.stderr
