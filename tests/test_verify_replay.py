"""``lrcc verify`` and ``lrcc replay`` (ADR-0013): what is stored against the log, and offline.

Each test stores a run against the mocked transport, then damages something on purpose and
checks that the damage is named. Replay is run with the network switched off in the
configuration, which is how "a replay asks nothing" is asserted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import duckdb
import httpx
import pytest
import respx
from typer.testing import CliRunner, Result

from lrcc.adapters.sources.arxiv import API, ArxivSource
from lrcc.domain.record import Record
from lrcc.views.cli.app import app

runner = CliRunner()

NETWORK = {"enabled": True, "hosts": {"export.arxiv.org": {"min_interval": 0}}}


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def review_dir(workspace_root: Path) -> Path:
    """The folder of the review ``example``."""
    return workspace_root / "reviews" / "example"


@pytest.fixture
def offline(
    make_config: Callable[..., Path],
    workspace_root: Path,
    respx_mock: respx.MockRouter,
    fixture_bytes: Callable[[str], bytes],
) -> str:
    """One run is stored; the configuration returned has the network off."""
    online = str(make_config(workspace_root, network=NETWORK))
    lrcc("init", "example", "--config", online)
    feed = fixture_bytes("arxiv_feed.xml").replace(b">57<", b">2<")
    respx_mock.get(API).mock(return_value=httpx.Response(200, content=feed))
    stored = lrcc("search", "example", "--source", "arxiv", "--config", online)
    assert stored.exit_code == 0, stored.stderr
    respx_mock.reset()
    return str(make_config(workspace_root))


def _run_folder(review_dir: Path) -> Path:
    (folder,) = (review_dir / "runs").iterdir()
    return folder


def test_an_untouched_review_verifies(offline: str) -> None:
    """Every response and record matches the log."""
    result = lrcc("verify", "example", "--config", offline)
    assert result.exit_code == 0, result.stderr
    assert "1 run(s) and 1 stored response(s) checked" in result.stdout
    assert "Everything stored matches the log" in result.stdout


def test_an_edited_response_is_named(offline: str, review_dir: Path) -> None:
    """One changed byte in a stored answer no longer matches its digest."""
    response = _run_folder(review_dir) / "response-0001.raw"
    response.write_bytes(response.read_bytes() + b" ")
    result = lrcc("verify", "example", "--config", offline)
    assert result.exit_code == 1
    assert "response-0001.raw: does not match the digest in the log" in result.stdout


def test_a_missing_response_is_named(offline: str, review_dir: Path) -> None:
    """A deleted answer is reported, not skipped."""
    (_run_folder(review_dir) / "response-0001.raw").unlink()
    data = json.loads(lrcc("verify", "example", "--config", offline, "--json").stdout)
    assert data["verified"] is False
    assert data["problems"][0].endswith("response-0001.raw: is missing")


def test_what_the_log_does_not_know_is_named(offline: str, review_dir: Path) -> None:
    """A file or a run folder nobody logged is reported."""
    (_run_folder(review_dir) / "extra.txt").write_text("added by hand", encoding="utf-8")
    (review_dir / "runs" / "0099-stray").mkdir()
    result = lrcc("verify", "example", "--config", offline)
    assert result.exit_code == 1
    assert "extra.txt: is not named by the log" in result.stdout
    assert "runs/0099-stray: no log entry names this folder" in result.stdout


def test_edited_records_are_named(offline: str, review_dir: Path) -> None:
    """The records table is checked against the digest the log holds."""
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute("UPDATE records SET title = ? WHERE position = 1", ["edited by hand"])
    connection.close()
    result = lrcc("verify", "example", "--config", offline)
    assert result.exit_code == 1
    assert "the records in the database do not match the log" in result.stdout


def test_a_log_that_names_a_file_outside_the_review_is_refused(
    offline: str, review_dir: Path
) -> None:
    """File names come from the log, which may be edited; they never leave the runs folder."""
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute(
        "UPDATE runs SET entry = replace(entry, ?, ?)",
        ["response-0001.raw", "../../../protocol.yaml"],
    )
    connection.close()
    result = lrcc("verify", "example", "--config", offline)
    assert result.exit_code == 1
    assert "names a response outside the review" in result.stderr


def test_a_replay_reproduces_a_run_with_the_network_off(
    offline: str, respx_mock: respx.MockRouter
) -> None:
    """The records are rederived from the stored answers, and nothing is requested."""
    result = lrcc("replay", "example", "--config", offline)
    assert result.exit_code == 0, result.stderr
    assert "logged 2  replayed 2  identical" in result.stdout
    assert "Every run is reproduced" in result.stdout
    assert respx_mock.calls.call_count == 0


def test_a_replay_says_when_the_code_derives_something_else(
    offline: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If today's code reads fewer or different records from the same answers, it is reported."""
    derive = ArxivSource.records_from

    def fewer(self: ArxivSource, bodies: list[bytes]) -> tuple[Record, ...]:
        return derive(self, bodies)[:1]

    monkeypatch.setattr(ArxivSource, "records_from", fewer)
    result = lrcc("replay", "example", "--config", offline)
    assert result.exit_code == 1
    assert "logged 2  replayed 1  DIFFERENT" in result.stdout

    data = json.loads(lrcc("replay", "example", "--config", offline, "--json").stdout)
    assert data["identical"] is False
    assert data["runs"][0]["replayed"] == 1


def test_a_replay_refuses_a_changed_response(offline: str, review_dir: Path) -> None:
    """A replay of altered answers would prove nothing, so it stops and points at verify."""
    response = _run_folder(review_dir) / "response-0001.raw"
    response.write_bytes(response.read_bytes() + b" ")
    result = lrcc("replay", "example", "--config", offline)
    assert result.exit_code == 1
    assert "does not match the digest in the log; run verify" in result.stdout


def test_a_review_without_runs(make_config: Callable[..., Path], workspace_root: Path) -> None:
    """Both commands say there is nothing yet, and succeed."""
    config = str(make_config(workspace_root))
    lrcc("init", "example", "--config", config)
    assert lrcc("verify", "example", "--config", config).exit_code == 0
    replayed = lrcc("replay", "example", "--config", config)
    assert replayed.exit_code == 0
    assert "No runs are stored yet" in replayed.stdout
