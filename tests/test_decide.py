"""``lrcc candidates`` and ``lrcc decide`` (ADR-0018): a person confirms fuzzy duplicates.

The review holds two synthetic published records with DOIs, and two synthetic preprints without
one: a preprint of the first, and a paper by the same group on another question whose title is
close to the second's. Everything goes through the commands and the real DuckDB stores.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner, Result

from lrcc.views.cli.app import app

runner = CliRunner()

PUBLISHED = b"""TY  - JOUR
TI  - Cross-Modal Distillation for Tumour Segmentation
AU  - Example, Ada
PY  - 2023
DO  - 10.0000/SYNTHETIC.A
N1  - Synthetic: written for LRCC's tests.
ER  -

TY  - JOUR
TI  - A prognosis network for multimodal fusion in synthetic imaging
AU  - Sample, Gil
PY  - 2022
DO  - 10.0000/SYNTHETIC.B
N1  - Synthetic: written for LRCC's tests.
ER  -
"""

PREPRINTS = b"""TY  - JOUR
TI  - Cross-modal distillation for tumour segmentation
AU  - Example, Ada
PY  - 2022
N1  - Synthetic: written for LRCC's tests.
ER  -

TY  - JOUR
TI  - A diagnosis network for multimodal fusion in synthetic imaging
AU  - Sample, Gil
PY  - 2024
N1  - Synthetic: written for LRCC's tests.
ER  -
"""


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


def _import(config: str, tmp_path: Path, name: str, data: bytes, source: str) -> None:
    path = tmp_path / name
    path.write_bytes(data)
    result = lrcc(
        "import",
        "example",
        str(path),
        "--source",
        source,
        "--searched",
        "2026-09-30",
        "--reported",
        "2",
        "--config",
        config,
    )
    assert result.exit_code == 0, result.stdout + result.stderr


@pytest.fixture
def review(make_config: Callable[..., Path], workspace_root: Path, tmp_path: Path) -> str:
    """Four records in four works, deduplicated, and a reviewer in the configuration."""
    config = str(make_config(workspace_root, reviewer="Ada Example"))
    lrcc("init", "example", "--config", config)
    _import(config, tmp_path, "published.ris", PUBLISHED, "pubmed")
    _import(config, tmp_path, "preprints.ris", PREPRINTS, "arxiv")
    assert lrcc("dedupe", "example", "--config", config).exit_code == 0
    return config


def _pairs(config: str, path: Path) -> list[dict[str, str]]:
    result = lrcc("candidates", "example", "--csv", str(path), "--config", config)
    assert result.exit_code == 0, result.stdout + result.stderr
    return list(csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))


def _fill(path: Path, rows: list[dict[str, str]], decide: Callable[[dict[str, str]], str]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "decision": decide(row)})
    path.write_bytes(("﻿" + buffer.getvalue()).encode("utf-8"))


def _same_paper(row: dict[str, str]) -> str:
    return "same" if "distillation" in row["title_a"].lower() else "different"


def _decide(config: str, path: Path) -> Result:
    return lrcc("decide", "example", str(path), "--config", config, "--json")


def test_a_person_confirms_the_preprint_and_rejects_the_lookalike(
    review: str, tmp_path: Path
) -> None:
    """Two pairs proposed; one same, one different; the counts and the next listing follow."""
    path = tmp_path / "pairs.csv"
    rows = _pairs(review, path)
    assert [row["score"] for row in rows][0] == "1.000"
    assert len(rows) == 2
    _fill(path, rows, _same_paper)

    decided = json.loads(_decide(review, path).stdout)
    assert decided["recorded"] == {"same": 1, "different": 1}
    assert (decided["reviewer"], decided["groups"]) == ("Ada Example", 3)

    data = json.loads(lrcc("dedupe", "example", "--config", review, "--json").stdout)
    assert data["decisions"] == 2
    assert data["current_protocol"] == {
        "records": 4,
        "works": 4,
        "groups": 3,
        "duplicates": 1,
        "by_identifiers": 0,
        "by_person": 1,
    }
    listed = json.loads(lrcc("candidates", "example", "--config", review, "--json").stdout)
    assert listed["pairs"] == []

    again = json.loads(_decide(review, path).stdout)
    assert again["recorded"] == {"same": 0, "different": 0}
    assert again["unchanged"] == 2


def test_a_correction_is_a_new_entry(review: str, tmp_path: Path, workspace_root: Path) -> None:
    """Changing a decision appends; the latest is in force; the log keeps both."""
    path = tmp_path / "pairs.csv"
    rows = _pairs(review, path)
    _fill(path, rows, _same_paper)
    assert _decide(review, path).exit_code == 0
    _fill(path, rows, lambda row: "different")
    corrected = json.loads(_decide(review, path).stdout)
    assert corrected["recorded"] == {"same": 0, "different": 1}
    assert corrected["groups"] == 4

    database = workspace_root / "reviews" / "example" / "review.duckdb"
    connection = duckdb.connect(str(database), read_only=True)
    row = connection.execute("SELECT count(*) FROM decisions").fetchone()
    connection.close()
    assert row is not None and row[0] == 3


def test_verify_and_dedupe_name_an_edited_decision(
    review: str, tmp_path: Path, workspace_root: Path
) -> None:
    """The decisions' chain is checked like the runs'."""
    path = tmp_path / "pairs.csv"
    _fill(path, _pairs(review, path), _same_paper)
    assert _decide(review, path).exit_code == 0
    assert lrcc("verify", "example", "--config", review).exit_code == 0

    connection = duckdb.connect(str(workspace_root / "reviews" / "example" / "review.duckdb"))
    connection.execute("UPDATE decisions SET entry = replace(entry, '\"same\"', '\"different\"')")
    connection.close()
    verified = lrcc("verify", "example", "--config", review)
    assert verified.exit_code == 1
    assert "its content does not match its hash" in verified.stdout
    refused = lrcc("dedupe", "example", "--config", review, "--json")
    assert "the decisions log of 'example' does not verify" in json.loads(refused.stdout)["error"]


def _write(path: Path, *rows: tuple[str, str, str]) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["work_a", "work_b", "decision", "note"])
    writer.writerows([*row, ""] for row in rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return path


def _works(config: str, tmp_path: Path) -> tuple[str, str, str, str]:
    rows = _pairs(config, tmp_path / "listed.csv")
    same, lookalike = rows
    return same["work_a"], same["work_b"], lookalike["work_a"], lookalike["work_b"]


def _recorded(workspace_root: Path) -> int:
    database = workspace_root / "reviews" / "example" / "review.duckdb"
    connection = duckdb.connect(str(database), read_only=True)
    row = connection.execute("SELECT count(*) FROM decisions").fetchone()
    connection.close()
    return row[0] if row else 0


def test_files_that_cannot_be_recorded_record_nothing(
    review: str, tmp_path: Path, workspace_root: Path
) -> None:
    """A contradiction, a stranger, a pair twice, a work with itself: nothing is written."""
    a, b, c, _ = _works(review, tmp_path)
    cases = {
        "contradiction": (
            _write(tmp_path / "1.csv", (a, b, "same"), (a, c, "same"), (b, c, "different")),
            "contradicts itself or earlier decisions",
        ),
        "stranger": (
            _write(tmp_path / "2.csv", (a, "nobody2020-000000", "same")),
            "'nobody2020-000000' is not a work of 'example'",
        ),
        "twice": (
            _write(tmp_path / "3.csv", (a, b, "same"), (b, a, "different")),
            "appears earlier in the file with another decision",
        ),
        "itself": (_write(tmp_path / "4.csv", (a, a, "same")), "a work is paired with itself"),
    }
    for name, (path, expected) in cases.items():
        result = _decide(review, path)
        assert result.exit_code == 1, name
        assert expected in json.loads(result.stdout)["error"], name
    assert _recorded(workspace_root) == 0


def test_a_decision_needs_a_reviewer(
    make_config: Callable[..., Path], workspace_root: Path, review: str, tmp_path: Path
) -> None:
    """A decision is never attributed to nobody."""
    a, b, _, _ = _works(review, tmp_path)
    anonymous = str(make_config(workspace_root))
    result = lrcc(
        "decide", "example", str(_write(tmp_path / "x.csv", (a, b, "same"))), "--config", anonymous
    )
    assert result.exit_code == 1
    assert "recording a decision needs the reviewer's name" in result.stderr
    assert _recorded(workspace_root) == 0


def test_candidates_need_linked_records_and_a_new_file(
    review: str, tmp_path: Path, fixture_bytes: Callable[[str], bytes]
) -> None:
    """A run not yet deduplicated, or a file already there, stops the listing."""
    existing = tmp_path / "existing.csv"
    existing.write_text("keep me", encoding="utf-8")
    refused = lrcc("candidates", "example", "--csv", str(existing), "--config", review)
    assert refused.exit_code == 1
    assert "already exists" in refused.stderr
    assert existing.read_text(encoding="utf-8") == "keep me"

    _import(review, tmp_path, "more.ris", fixture_bytes("ieee_export.ris"), "pubmed")
    unlinked = lrcc("candidates", "example", "--config", review)
    assert unlinked.exit_code == 1
    assert "2 record(s) of 'example' are not linked to works yet" in unlinked.stderr


def test_a_row_left_empty_waits_and_unreadable_paths_are_named(
    review: str, tmp_path: Path, workspace_root: Path
) -> None:
    """A half-filled file records what is filled; a path that cannot be used is named."""
    a, b, c, d = _works(review, tmp_path)
    half = json.loads(
        _decide(review, _write(tmp_path / "half.csv", (a, b, "same"), (c, d, ""))).stdout
    )
    assert (half["recorded"]["same"], half["pending"]) == (1, 1)
    assert _recorded(workspace_root) == 1

    missing = _decide(review, tmp_path / "nowhere.csv")
    assert "cannot read" in json.loads(missing.stdout)["error"]
    unwritable = lrcc(
        "candidates", "example", "--csv", str(tmp_path / "no-folder" / "p.csv"), "--config", review
    )
    assert unwritable.exit_code == 1
    assert "cannot write" in unwritable.stderr


def test_the_text_output(review: str, tmp_path: Path) -> None:
    """The person sees each pair's titles, and where the file went."""
    path = tmp_path / "pairs.csv"
    listed = lrcc("candidates", "example", "--csv", str(path), "--config", review)
    assert "2 pair(s) of works with titles scoring 0.80 or more" in listed.stdout
    assert "Cross-Modal Distillation for Tumour Segmentation" in listed.stdout
    assert "lrcc decide example FILE" in listed.stdout
    _fill(
        path, list(csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig")))), _same_paper
    )
    decided = lrcc("decide", "example", str(path), "--config", review)
    assert "2 decision(s) recorded for Ada Example." in decided.stdout
    assert "The review's works now form 3 groups." in decided.stdout
    deduped = lrcc("dedupe", "example", "--config", review)
    assert "Duplicates removed: 0 by identifiers, 1 by a person." in deduped.stdout
