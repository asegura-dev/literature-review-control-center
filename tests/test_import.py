"""``lrcc import`` (ADR-0016): a database's RIS export stored as a run, then checked and replayed.

The commands build the real DuckDB store in a temporary workspace. The configuration keeps the
network off, and nothing is mocked: an import makes no request, and neither does its replay.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from lrcc.adapters.storage.duckdb_store import DuckDbReviewStore
from lrcc.domain.errors import ReviewError, SourceError
from lrcc.domain.workspace import open_workspace
from lrcc.features import imports
from lrcc.features.imports import import_run
from lrcc.views.cli.app import app

runner = CliRunner()

SCOPUS_STRING = 'TITLE-ABS-KEY("knowledge distillation")'


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def config(make_config: Callable[..., Path], workspace_root: Path) -> str:
    """The review ``example`` exists, its protocol has a Scopus string, and the network is off."""
    path = make_config(workspace_root)
    lrcc("init", "example", "--config", str(path))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["sources"]["scopus"] = {"query": SCOPUS_STRING}
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def review_dir(workspace_root: Path) -> Path:
    """The folder of the review ``example``."""
    return workspace_root / "reviews" / "example"


@pytest.fixture
def export(tmp_path: Path, fixture_bytes: Callable[[str], bytes]) -> Path:
    """The synthetic Scopus export, saved where a browser would put it."""
    path = tmp_path / "downloads" / "scopus.ris"
    path.parent.mkdir()
    path.write_bytes(fixture_bytes("scopus_export.ris"))
    return path


def _import(config: str, *files: Path, searched: str = "2026-09-30", reported: int = 2) -> Result:
    return lrcc(
        "import",
        "example",
        *(str(path) for path in files),
        "--source",
        "scopus",
        "--searched",
        searched,
        "--reported",
        str(reported),
        "--config",
        config,
        "--json",
    )


def test_an_export_is_stored_as_a_run(config: str, review_dir: Path, export: Path) -> None:
    """The file is kept byte for byte, and the run records the string and the day of the search."""
    result = _import(config, export)
    assert result.exit_code == 0, result.stdout + result.stderr
    run = json.loads(result.stdout)

    assert re.fullmatch(r"0001-\d{8}T\d{6}Z-scopus", run["run_id"])
    assert run["imported"] == {"format": "ris", "searched_on": "2026-09-30"}
    assert run["query"] == SCOPUS_STRING
    assert (run["reported"], run["retrieved"], run["complete"]) == (2, 2, True)
    (response,) = run["responses"]
    assert response["url"] == "scopus.ris"
    stored = review_dir / "runs" / run["run_id"] / response["file"]
    assert stored.read_bytes() == export.read_bytes()
    assert response["sha256"] == hashlib.sha256(export.read_bytes()).hexdigest()

    records = DuckDbReviewStore(review_dir).records(run["run_id"])
    assert [record.source_id for record in records] == [
        "2-s2.0-90000000001",
        "2-s2.0-90000000002",
    ]


def test_status_verify_and_replay_accept_an_import(config: str, export: Path) -> None:
    """An imported run is listed, verified and replayed like any other, with no network."""
    assert _import(config, export).exit_code == 0

    status = lrcc("status", "example", "--config", config)
    assert status.exit_code == 0, status.stderr
    assert "export searched 2026-09-30" in status.stdout
    (run,) = json.loads(lrcc("status", "example", "--config", config, "--json").stdout)["runs"]
    assert (run["imported"], run["searched_on"]) == (True, "2026-09-30")

    verified = lrcc("verify", "example", "--config", config)
    assert verified.exit_code == 0, verified.stdout + verified.stderr
    replayed = lrcc("replay", "example", "--config", config)
    assert replayed.exit_code == 0, replayed.stdout + replayed.stderr
    assert "logged 2  replayed 2  identical" in replayed.stdout


def test_a_search_exported_in_parts_is_one_run(
    config: str, review_dir: Path, tmp_path: Path, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Several files make one run, and their records keep the order the files were given."""
    text = fixture_bytes("scopus_export.ris").decode().replace("\r\n", "\n")
    first, second = (tmp_path / "part-1.ris", tmp_path / "part-2.ris")
    head, tail = text.split("\n\n")
    first.write_text(head + "\n", encoding="utf-8")
    second.write_text(tail, encoding="utf-8")

    result = _import(config, first, second)
    assert result.exit_code == 0, result.stdout + result.stderr
    run = json.loads(result.stdout)
    assert [response["url"] for response in run["responses"]] == ["part-1.ris", "part-2.ris"]
    records = DuckDbReviewStore(review_dir).records(run["run_id"])
    assert [record.year for record in records] == [2020, 2018]


def test_an_export_holding_less_than_reported_is_incomplete(config: str, export: Path) -> None:
    """A truncated export is stored, because it happened, but never looks complete."""
    result = lrcc(
        "import",
        "example",
        str(export),
        "--source",
        "scopus",
        "--searched",
        "2026-09-30",
        "--reported",
        "3",
        "--config",
        config,
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Incomplete: scopus reported 3 records and the files hold 2." in result.stdout
    assert "incomplete" in lrcc("status", "example", "--config", config).stdout


def test_a_file_already_stored_is_refused(config: str, review_dir: Path, export: Path) -> None:
    """Importing the same export twice would count its records twice."""
    first = json.loads(_import(config, export).stdout)
    again = _import(config, export)
    assert again.exit_code == 1
    assert f"is already stored, in run {first['run_id']}" in again.stdout
    assert len(DuckDbReviewStore(review_dir).log()) == 1


def test_the_same_file_twice_in_one_command_is_refused(
    config: str, review_dir: Path, export: Path, tmp_path: Path
) -> None:
    """Two files with the same bytes are one file given twice, and nothing is stored."""
    copy = tmp_path / "copy.ris"
    copy.write_bytes(export.read_bytes())
    result = _import(config, export, copy)
    assert result.exit_code == 1
    assert "copy.ris holds the same bytes as a file given before it" in result.stdout
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"Authors,Title\nExample A.,A title\n", "bad.ris is not a RIS file"),
        (b"TY  - JOUR\nTI  - cut short\n", "bad.ris ends inside a record"),
    ],
    ids=["csv", "cut-short"],
)
def test_a_broken_file_stores_nothing(
    config: str, review_dir: Path, tmp_path: Path, content: bytes, expected: str
) -> None:
    """The file is refused before anything is written: no folder, no entry, no database."""
    bad = tmp_path / "bad.ris"
    bad.write_bytes(content)
    result = _import(config, bad)
    assert result.exit_code == 1
    assert expected in json.loads(result.stdout)["error"]
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


def test_a_missing_or_oversized_file_is_named(
    config: str, export: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path that is not there, or a file past the ceiling, is refused with its name."""
    missing = _import(config, tmp_path / "nowhere.ris")
    assert missing.exit_code == 1
    assert "cannot read" in json.loads(missing.stdout)["error"]

    monkeypatch.setattr(imports, "MAX_EXPORT_BYTES", 10)
    oversized = _import(config, export)
    assert oversized.exit_code == 1
    assert "scopus.ris is larger than" in json.loads(oversized.stdout)["error"]


def test_a_source_the_protocol_does_not_name_is_refused(
    make_config: Callable[..., Path], workspace_root: Path, export: Path
) -> None:
    """The run records the protocol's string, so there must be one for that source."""
    config = str(make_config(workspace_root))
    lrcc("init", "example", "--config", config)
    result = _import(config, export)
    assert result.exit_code == 1
    assert "has no search string for scopus" in json.loads(result.stdout)["error"]


def test_a_day_in_the_future_is_refused(config: str, export: Path) -> None:
    """The day of the search cannot come after the import."""
    result = _import(config, export, searched="2999-01-01")
    assert result.exit_code == 1
    assert "is in the future" in json.loads(result.stdout)["error"]


def test_tomorrow_is_accepted_for_the_time_zones_ahead(
    config: str, workspace_root: Path, export: Path
) -> None:
    """At 23:00 UTC it is already tomorrow east of UTC; the day after is refused."""
    workspace = open_workspace(workspace_root, {})
    store = DuckDbReviewStore(workspace.review_dir("example"))

    def late() -> datetime:
        return datetime(2026, 9, 30, 23, 0, tzinfo=UTC)

    outcome = import_run(
        workspace, "example", "scopus", [export], date(2026, 10, 1), 2, store, late
    )
    assert outcome.logged.run.searched_on == "2026-10-01"
    with pytest.raises(ReviewError, match="is in the future"):
        import_run(workspace, "example", "scopus", [export], date(2026, 10, 2), 2, store, late)


def test_an_import_needs_a_file(config: str, workspace_root: Path) -> None:
    """Called without a file, the feature refuses rather than store an empty run."""
    workspace = open_workspace(workspace_root, {})
    store = DuckDbReviewStore(workspace.review_dir("example"))
    with pytest.raises(ReviewError, match="no exported file was given"):
        import_run(workspace, "example", "scopus", [], date(2026, 9, 30), 0, store)
    with pytest.raises(SourceError, match="cannot read"):
        import_run(workspace, "example", "scopus", [workspace_root], date(2026, 9, 30), 0, store)
