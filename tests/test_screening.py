"""Title and abstract screening (ADR-0019): the order, the pilot, decisions and their log.

The command tests import synthetic records, deduplicate them and screen them through the real
DuckDB stores. The interactive session is driven by keystrokes given as input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml
from typer.testing import CliRunner, Result

from lrcc.domain.errors import ReviewError
from lrcc.domain.gold import parse_gold_set
from lrcc.domain.runs import GENESIS, entry_hash
from lrcc.domain.screening import (
    PILOT_SIZE,
    LoggedScreen,
    ScreenDecision,
    check_verdict,
    frontier_groups,
    pilot_groups,
    screened,
    screening_chain_problems,
    screening_order,
)
from lrcc.views.cli.app import app

runner = CliRunner()


def _decision(work_id: str, verdict: str = "include", code: str | None = None) -> ScreenDecision:
    return ScreenDecision.model_validate(
        {
            "work_id": work_id,
            "decision": verdict,
            "code": code,
            "note": "",
            "pilot": False,
            "protocol_sha256": "p" * 64,
            "reviewer": "Ada Example",
            "decided_at": "2026-10-01T00:00:00Z",
        }
    )


def _log(*decisions: ScreenDecision) -> list[LoggedScreen]:
    log, prev = [], GENESIS
    for decision in decisions:
        entry = decision.entry()
        hashed = entry_hash(prev, entry)
        log.append(LoggedScreen(decision=decision, entry=entry, prev_hash=prev, entry_hash=hashed))
        prev = hashed
    return log


# --- the domain


def test_the_order_is_the_hash_of_review_and_work() -> None:
    """Stateless and reproducible; another review orders the same works apart."""
    works = [f"w{n}" for n in range(20)]
    order = screening_order("one", works)
    expected = sorted(works, key=lambda w: hashlib.sha256(f"one|{w}".encode()).hexdigest())
    assert order == expected
    assert screening_order("one", reversed(works)) == order
    assert screening_order("two", works) != order


def test_the_pilot_is_the_first_of_the_order_plus_the_frontier() -> None:
    """Frontier cases beyond the first 50 join the pilot, in their order."""
    order = [f"w{n:03d}" for n in range(80)]
    pilot = pilot_groups(order, ["w070", "w010"])
    assert len(pilot) == PILOT_SIZE + 1
    assert pilot[-1] == "w070"
    assert pilot_groups(order[:5], []) == order[:5]


def test_frontier_cases_are_found_by_their_identifiers() -> None:
    """A DOI or an arXiv id names the work; a case the searches missed is named, not added."""
    frontier = parse_gold_set(
        b'format: 1\nworks:\n  - label: Found\n    doi: "10.0000/A"\n'
        b'  - label: Preprint\n    arxiv: "2401.00001"\n  - label: Missed\n    doi: "10.0000/Z"\n',
        "frontier.yaml",
    )
    identifiers = {"doi:10.0000/a": "a2020-aaaaaa", "arxiv:2401.00001": "b2024-bbbbbb"}
    group_of = {"a2020-aaaaaa": "a2020-aaaaaa", "b2024-bbbbbb": "c2025-cccccc"}
    found, missing = frontier_groups(frontier, identifiers, group_of)
    assert found == {"Found": "a2020-aaaaaa", "Preprint": "c2025-cccccc"}
    assert missing == ["Missed"]


def test_a_group_s_decision_is_the_latest_on_any_of_its_works() -> None:
    """A correction is a new entry; a decision on a merged work speaks for its group."""
    group_of = {"a": "a", "b": "a", "c": "c"}
    log = _log(_decision("a"), _decision("b", "exclude", "EXC1"), _decision("x"))
    decided = screened(log, group_of)
    assert list(decided) == ["a"]
    assert (decided["a"].work_id, decided["a"].decision) == ("b", "exclude")


@pytest.mark.parametrize(
    ("verdict", "code", "expected"),
    [
        ("exclude", None, "an exclusion needs one of the protocol's codes"),
        ("exclude", "EXC9", "an exclusion needs one of the protocol's codes"),
        ("include", "EXC1", "only an exclusion cites a code"),
        ("maybe", None, "'maybe' is not a decision"),
    ],
    ids=["no-code", "unknown-code", "code-on-include", "unknown-verdict"],
)
def test_a_decision_the_protocol_cannot_carry_is_refused(
    verdict: str, code: str | None, expected: str
) -> None:
    """Only exclusions cite a code, and only a code the protocol defines."""
    with pytest.raises(ReviewError, match=expected):
        check_verdict(verdict, code, {"EXC1": "Single modality"})
    check_verdict("exclude", "EXC1", {"EXC1": "Single modality"})
    check_verdict("uncertain", None, {"EXC1": "Single modality"})


def test_the_screening_chain_names_an_edit() -> None:
    """The same chain as the other logs."""
    log = _log(_decision("a"), _decision("b"))
    assert screening_chain_problems(log) == []
    edited = log[1].entry.replace('"include"', '"exclude"')
    log[1] = LoggedScreen(
        decision=ScreenDecision.model_validate_json(edited),
        entry=edited,
        prev_hash=log[1].prev_hash,
        entry_hash=log[1].entry_hash,
    )
    assert screening_chain_problems(log) == ["screening 2 (b): its content does not match its hash"]


# --- the commands


def _ris(count: int) -> bytes:
    records = [
        f"TY  - JOUR\nTI  - Synthetic study {chr(65 + n)} on distinct imaging\nAU  - Example, Ada\n"
        f"PY  - 2024\nDO  - 10.0000/SCREEN.{n}\nAB  - An invented abstract number {n}.\n"
        "N1  - Synthetic: written for LRCC's tests.\nER  -\n"
        for n in range(count)
    ]
    return "\n".join(records).encode()


def lrcc(*args: str, input: str | None = None) -> Result:
    """Run ``lrcc`` with ``args`` and optional keystrokes, with ``LRCC_CONFIG`` unset."""
    return runner.invoke(app, list(args), input=input, env={"LRCC_CONFIG": None})


@pytest.fixture
def review(make_config: Callable[..., Path], workspace_root: Path, tmp_path: Path) -> str:
    """Four synthetic works from PubMed, deduplicated, with a reviewer configured."""
    config = str(make_config(workspace_root, reviewer="Ada Example"))
    lrcc("init", "example", "--config", config)
    export = tmp_path / "four.ris"
    export.write_bytes(_ris(4))
    imported = lrcc(
        "import", "example", str(export), "--source", "pubmed", "--searched", "2026-10-01",
        "--reported", "4", "--config", config,
    )  # fmt: skip
    assert imported.exit_code == 0, imported.stdout + imported.stderr
    assert lrcc("dedupe", "example", "--config", config).exit_code == 0
    return config


def _report(config: str) -> dict[str, Any]:
    result = lrcc("screen-report", "example", "--config", config, "--json")
    assert result.exit_code == 0, result.stdout + result.stderr
    data: dict[str, Any] = json.loads(result.stdout)
    return data


def _works(config: str) -> list[str]:
    session = lrcc("screen", "example", "--config", config, input="q\n")
    return [line.split()[3] for line in session.stdout.splitlines() if line.startswith("[1 of")]


def test_a_session_records_each_decision_and_resumes(review: str) -> None:
    """Include, exclude with a code, uncertain, then stop: three entries, one work left."""
    session = lrcc("screen", "example", "--config", review, input="i\ne\nEXC1\nu\nq\n")
    assert session.exit_code == 0, session.stdout + session.stderr
    assert "4 of 4 work(s) to go" in session.stdout
    assert "Stopped. 3 decision(s) recorded." in session.stdout
    overall = _report(review)["overall"]
    assert overall == {
        "groups": 4,
        "include": 1,
        "exclude": 1,
        "uncertain": 1,
        "pending": 1,
        "excluded_by_code": {"EXC1": 1},
    }
    resumed = lrcc("screen", "example", "--config", review, input="i\n")
    assert "1 of 4 work(s) to go" in resumed.stdout
    assert "Done. 1 decision(s) recorded." in resumed.stdout


def test_the_session_shows_the_work_and_forgives_a_slip(review: str) -> None:
    """The abstract is shown; an unknown key or code records nothing; a note is kept."""
    result = lrcc(
        "screen", "example", "--config", review,
        input="x\ne\nEXC99\nn\nborderline\nu\nq\n",
    )  # fmt: skip
    assert "An invented abstract number" in result.stdout
    assert "Unknown key" in result.stdout
    assert "an exclusion needs one of the protocol's codes" in result.stderr
    recorded = lrcc("screen", "example", "--config", review, "--json", input="q\n")
    assert "--json needs --work" in json.loads(recorded.stdout)["error"]
    overall = _report(review)["overall"]
    assert (overall["uncertain"], overall["pending"]) == (1, 3)


def test_one_decision_without_the_session(review: str, workspace_root: Path) -> None:
    """--work decides one; a correction is a new entry; what cannot be recorded is refused."""
    first = _works(review)[0]
    once = lrcc(
        "screen", "example", "--work", first, "--decision", "include", "--config", review, "--json"
    )
    assert json.loads(once.stdout)["decision"] == "include"
    again = lrcc(
        "screen", "example", "--work", first, "--decision", "exclude", "--code", "EXC2",
        "--note", "a second look", "--config", review, "--json",
    )  # fmt: skip
    assert json.loads(again.stdout)["note"] == "a second look"
    assert _report(review)["overall"]["excluded_by_code"] == {"EXC2": 1}

    refusals = {
        ("--decision", "include", "--code", "EXC1"): "only an exclusion cites a code",
        ("--decision", "exclude"): "an exclusion needs one of the protocol's codes",
        (): "--work needs --decision",
    }
    for flags, expected in refusals.items():
        result = lrcc("screen", "example", "--work", first, *flags, "--config", review, "--json")
        assert expected in json.loads(result.stdout)["error"], flags
    stranger = lrcc(
        "screen", "example", "--work", "nobody2020-000000", "--decision", "include",
        "--config", review, "--json",
    )  # fmt: skip
    assert "is not a work 'example' screens" in json.loads(stranger.stdout)["error"]

    database = workspace_root / "reviews" / "example" / "review.duckdb"
    connection = duckdb.connect(str(database), read_only=True)
    row = connection.execute("SELECT count(*) FROM screening").fetchone()
    connection.close()
    assert row is not None and row[0] == 2


def test_the_pilot_and_its_frontier(review: str, workspace_root: Path) -> None:
    """Pilot decisions are marked; a frontier case the searches missed is named."""
    frontier = workspace_root / "reviews" / "example" / "frontier.yaml"
    frontier.write_text(
        'format: 1\nworks:\n  - label: Known\n    doi: "10.0000/SCREEN.1"\n'
        '  - label: Never found\n    doi: "10.0000/NOWHERE"\n',
        encoding="utf-8",
    )
    session = lrcc("screen", "example", "--pilot", "--config", review, input="u\nq\n")
    assert "(pilot): 4 of 4 work(s) to go" in session.stdout
    assert "frontier case the searches did not find: Never found" in session.stdout
    report = _report(review)
    assert report["pilot"]["uncertain"] == 1
    assert report["frontier_not_found"] == ["Never found"]
    marked = lrcc(
        "screen", "example", "--pilot", "--work", _works(review)[0], "--decision", "include",
        "--config", review, "--json",
    )  # fmt: skip
    assert json.loads(marked.stdout)["pilot"] is True


def test_an_amendment_is_visible_and_kept(review: str, workspace_root: Path) -> None:
    """Each decision names its protocol, and every protocol used is kept by its digest."""
    review_dir = workspace_root / "reviews" / "example"
    lrcc("screen", "example", "--config", review, input="i\nq\n")
    protocol = review_dir / "protocol.yaml"
    data = yaml.safe_load(protocol.read_text(encoding="utf-8"))
    data["criteria"].append({"code": "EXC9", "text": "An exclusion added after the pilot."})
    protocol.write_text(yaml.safe_dump(data), encoding="utf-8")
    lrcc("screen", "example", "--config", review, input="e\nEXC9\nq\n")

    report = _report(review)
    versions = report["decisions_by_protocol"]
    assert sorted(versions.values()) == [1, 1]
    kept = sorted(path.name for path in (review_dir / "protocols").iterdir())
    assert kept == sorted(f"{digest}.yaml" for digest in versions)
    assert report["overall"]["excluded_by_code"] == {"EXC9": 1}
    assert lrcc("verify", "example", "--config", review).exit_code == 0


def test_verify_and_the_session_name_edits(review: str, workspace_root: Path) -> None:
    """An edited decision breaks the chain; an edited protocol copy no longer fits its name."""
    review_dir = workspace_root / "reviews" / "example"
    lrcc("screen", "example", "--config", review, input="i\nq\n")
    (copy,) = (review_dir / "protocols").iterdir()
    copy.write_bytes(copy.read_bytes() + b"\n# edited\n")
    connection = duckdb.connect(str(review_dir / "review.duckdb"))
    connection.execute("UPDATE screening SET entry = replace(entry, 'include', 'exclude')")
    connection.close()

    verified = lrcc("verify", "example", "--config", review)
    assert verified.exit_code == 1
    assert "screening 1 (" in verified.stdout
    assert f"protocols/{copy.name}: its content does not match its name" in verified.stdout
    refused = lrcc("screen", "example", "--config", review, "--json", input="q\n")
    assert "the screening log of 'example' does not verify" in json.loads(refused.stdout)["error"]


def test_screening_needs_a_reviewer(
    make_config: Callable[..., Path], workspace_root: Path, review: str
) -> None:
    """A decision is never attributed to nobody."""
    anonymous = str(make_config(workspace_root))
    result = lrcc("screen", "example", "--config", anonymous, input="i\n")
    assert result.exit_code == 1
    assert "recording a decision needs the reviewer's name" in result.stderr


def test_the_text_report(review: str) -> None:
    """The person reads the tallies, the order rule and the protocol in force."""
    lrcc("screen", "example", "--config", review, input="e\nEXC2\nq\n")
    report = lrcc("screen-report", "example", "--config", review)
    assert (
        "overall  4 works: include 0, exclude 1 (EXC2 1), uncertain 0, pending 3" in report.stdout
    )
    assert "by the SHA-256 of 'example|work_id'" in report.stdout
    assert "(the protocol in force)" in report.stdout
    assert "reviewer Ada Example" in report.stdout
