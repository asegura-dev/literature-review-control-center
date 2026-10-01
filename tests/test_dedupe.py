"""``lrcc dedupe`` (ADR-0017): exact duplicates joined into works, through the real stores.

Runs are stored by importing synthetic RIS exports, so no transport is mocked and the network
stays off. The catalog is the real DuckDB file in the temporary workspace's library.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest
import yaml
from typer.testing import CliRunner, Result

from lrcc.adapters.storage.duckdb_catalog import DuckDbWorkCatalog
from lrcc.adapters.storage.duckdb_store import DuckDbReviewStore
from lrcc.domain.errors import StoreError
from lrcc.domain.works import Work
from lrcc.views.cli.app import app

runner = CliRunner()

#: Two synthetic records already met: the first Scopus record's DOI, and the second's title.
AGAIN = b"""TY  - JOUR
TI  - A synthetic Scopus title, as another database writes it
AU  - A. Example
PY  - 2020
DO  - 10.0000/SYNTHETIC.SCOPUS.1
N1  - Synthetic: written for LRCC's tests.
ER  -

TY  - CONF
TI  - A Second Synthetic Scopus Title
AU  - A. Specimen
PY  - 2018
N1  - Synthetic: written for LRCC's tests.
ER  -
"""

#: One record whose DOI is one work's and whose EID is another's.
CONFLICT = b"""TY  - JOUR
TI  - A synthetic record that names two works
PY  - 2021
DO  - 10.0000/SYNTHETIC.IEEE.1
UR  - https://www.scopus.com/inward/record.uri?eid=2-s2.0-90000000002&partnerID=40
N1  - Synthetic: written for LRCC's tests.
ER  -
"""


def lrcc(*args: str) -> Result:
    """Run ``lrcc`` with ``args``, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), env={"LRCC_CONFIG": None})


@pytest.fixture
def config(make_config: Callable[..., Path], workspace_root: Path) -> str:
    """The review ``example``, with Scopus and IEEE Xplore strings, and the network off."""
    path = make_config(workspace_root)
    lrcc("init", "example", "--config", str(path))
    protocol = workspace_root / "reviews" / "example" / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["sources"]["scopus"] = {"query": 'TITLE-ABS-KEY("knowledge distillation")'}
    data["sources"]["ieee"] = {"query": "distillation AND MRI"}
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def review_dir(workspace_root: Path) -> Path:
    """The folder of the review ``example``."""
    return workspace_root / "reviews" / "example"


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
def three_runs(config: str, tmp_path: Path, fixture_bytes: Callable[[str], bytes]) -> str:
    """Scopus, IEEE Xplore, and IEEE Xplore again with two records already met."""
    _import(config, tmp_path, "scopus.ris", fixture_bytes("scopus_export.ris"), "scopus")
    _import(config, tmp_path, "ieee.ris", fixture_bytes("ieee_export.ris"), "ieee")
    _import(config, tmp_path, "again.ris", AGAIN, "ieee")
    return config


def _dedupe(config: str) -> Result:
    return lrcc("dedupe", "example", "--config", config, "--json")


def test_exact_duplicates_are_joined_with_their_reasons(
    three_runs: str, review_dir: Path, workspace_root: Path
) -> None:
    """Six records make four works: one joined by DOI, one by title, each reason kept."""
    result = _dedupe(three_runs)
    assert result.exit_code == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["linked_now"] == 6
    assert data["joined_by"] == {"doi": 1, "title": 1}
    assert (data["works"], data["unstable"]) == (4, 2)
    assert data["current_protocol"] == {"records": 6, "works": 4, "duplicates": 2}
    assert [(run["first_seen"], run["already_seen"]) for run in data["runs"]] == [
        (2, 0),
        (2, 0),
        (0, 2),
    ]

    links = DuckDbReviewStore(review_dir).links()
    assert [link.matched_by for link in links[-2:]] == [
        "doi:10.0000/synthetic.scopus.1",
        "title:a second synthetic scopus title|2018",
    ]
    assert links[-2].work_id == links[0].work_id
    assert links[-1].work_id == links[1].work_id
    assert all(re.fullmatch(r"[a-z]+(\d{4}|nd)-[0-9a-f]{6}", link.work_id) for link in links)
    assert (workspace_root / "library" / "catalog.duckdb").is_file()


def test_the_text_report_names_the_prisma_numbers(three_runs: str) -> None:
    """The person sees the duplicates removed under the current protocol."""
    result = lrcc("dedupe", "example", "--config", three_runs)
    assert result.exit_code == 0, result.stderr
    assert "joined a work already named, by: doi 1, title 1" in result.stdout
    assert "Runs under the current protocol: 6 records, 4 works, 2 duplicates removed." in (
        result.stdout
    )
    assert "The review holds 4 works. 2 of them are named from a title" in result.stdout


def test_the_prisma_numbers_count_only_runs_under_the_current_protocol(
    config: str, tmp_path: Path, review_dir: Path, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Runs made before the protocol changed still give works, but not the current counts."""
    _import(config, tmp_path, "scopus.ris", fixture_bytes("scopus_export.ris"), "scopus")
    protocol = review_dir / "protocol.yaml"
    protocol.write_bytes(protocol.read_bytes() + b"\n# fixed before the definitive runs\n")
    _import(config, tmp_path, "again.ris", AGAIN, "ieee")

    data = json.loads(_dedupe(config).stdout)
    assert [run["current_protocol"] for run in data["runs"]] == [False, True]
    assert data["works"] == 2
    assert data["current_protocol"] == {"records": 2, "works": 2, "duplicates": 0}


def test_a_second_pass_links_only_what_is_new(
    three_runs: str, tmp_path: Path, fixture_bytes: Callable[[str], bytes]
) -> None:
    """Nothing is linked twice, and a new run joins the works that exist."""
    assert _dedupe(three_runs).exit_code == 0
    assert json.loads(_dedupe(three_runs).stdout)["linked_now"] == 0

    again = fixture_bytes("ieee_export.ris").replace(b"2020 Synthetic", b"2020 Another")
    _import(three_runs, tmp_path, "rerun.ris", again, "ieee")
    data = json.loads(_dedupe(three_runs).stdout)
    assert data["linked_now"] == 2
    # The record without a DOI is found again by IEEE Xplore's own identifier, before its title.
    assert data["joined_by"] == {"doi": 1, "ieee": 1}
    assert data["works"] == 4


def test_a_record_naming_two_works_writes_nothing(
    three_runs: str, tmp_path: Path, review_dir: Path, workspace_root: Path
) -> None:
    """The conflict is refused and named; the links and the catalog stay as they were."""
    assert _dedupe(three_runs).exit_code == 0
    catalog = DuckDbWorkCatalog(workspace_root / "library" / "catalog.duckdb")
    before = catalog.identifiers()
    _import(three_runs, tmp_path, "conflict.ris", CONFLICT, "scopus")

    result = _dedupe(three_runs)
    assert result.exit_code == 1
    assert "carries identifiers of two works" in json.loads(result.stdout)["error"]
    assert len(DuckDbReviewStore(review_dir).links()) == 6
    assert catalog.identifiers() == before


def test_edited_records_or_an_edited_log_are_refused(three_runs: str, review_dir: Path) -> None:
    """Works built on altered data would prove nothing."""
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute("UPDATE records SET title = ? WHERE position = 1", ["edited by hand"])
    connection.close()
    edited = _dedupe(three_runs)
    assert edited.exit_code == 1
    assert "do not match the log" in json.loads(edited.stdout)["error"]

    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute("UPDATE runs SET entry = replace(entry, '\"reported\":2', '\"reported\":9')")
    connection.close()
    broken = _dedupe(three_runs)
    assert broken.exit_code == 1
    assert "does not verify" in json.loads(broken.stdout)["error"]


def test_a_record_is_linked_once(three_runs: str, review_dir: Path) -> None:
    """The review's database refuses a second link for the same record, and keeps the first."""
    assert _dedupe(three_runs).exit_code == 0
    store = DuckDbReviewStore(review_dir)
    first = store.links()[0]
    with pytest.raises(StoreError, match="already links"):
        store.save_links([first.model_copy(update={"work_id": "other2020-cccccc"})])
    assert store.links()[0] == first


def test_a_lost_catalog_is_named(three_runs: str, workspace_root: Path) -> None:
    """Links that point at works the catalog no longer holds are reported, not hidden."""
    assert _dedupe(three_runs).exit_code == 0
    (workspace_root / "library" / "catalog.duckdb").unlink()
    result = _dedupe(three_runs)
    assert result.exit_code == 1
    assert "the catalog does not hold 4 of the works" in json.loads(result.stdout)["error"]


def test_a_review_without_runs_creates_nothing(
    config: str, review_dir: Path, workspace_root: Path
) -> None:
    """No run, no work: neither the catalog nor the review's database is created."""
    data = json.loads(_dedupe(config).stdout)
    assert (data["linked_now"], data["works"]) == (0, 0)
    assert not (workspace_root / "library" / "catalog.duckdb").exists()
    assert sorted(path.name for path in review_dir.iterdir()) == ["protocol.yaml"]


def test_the_catalog_refuses_one_identifier_for_two_works(tmp_path: Path) -> None:
    """One identifier names one work, and the database itself holds to it (ADR-0006)."""
    catalog = DuckDbWorkCatalog(tmp_path / "library" / "catalog.duckdb")
    first = Work(work_id="one2020-aaaaaa", identity="doi:10.0000/x", unstable=False)
    second = Work(work_id="two2020-bbbbbb", identity="doi:10.0000/y", unstable=False)
    catalog.add([first], {"doi:10.0000/x": first.work_id}, "2026-10-01T00:00:00Z")
    with pytest.raises(StoreError, match="already taken"):
        catalog.add([second], {"doi:10.0000/x": second.work_id}, "2026-10-01T00:00:01Z")
    assert list(catalog.works()) == ["one2020-aaaaaa"]
    assert catalog.identifiers() == {"doi:10.0000/x": "one2020-aaaaaa"}
