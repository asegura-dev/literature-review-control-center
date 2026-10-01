"""Candidate pairs, a person's decisions, groups, and the CSV round trip (ADR-0018)."""

from __future__ import annotations

import csv
import io

import pytest

from lrcc.domain.errors import ReviewError
from lrcc.domain.fuzzy import (
    DIFFERENT,
    SAME,
    LoggedDecision,
    PairDecision,
    WorkFacts,
    candidate_pairs,
    contradictions,
    current_decisions,
    decision_chain_problems,
    groups,
    pair_of,
    score,
)
from lrcc.domain.pairs_csv import FIELDS, read_pairs, safe_cell, write_pairs
from lrcc.domain.runs import GENESIS, entry_hash


def _facts(work_id: str, *titles: str, doi: str | None = None) -> WorkFacts:
    return WorkFacts(
        work_id=work_id,
        titles=titles,
        title=titles[0],
        first_author="Example, Ada",
        year=2024,
        sources=("arxiv",),
        doi=doi,
    )


def _decision(first: str, second: str, verdict: str, reviewer: str = "Ada") -> PairDecision:
    a, b = pair_of(first, second)
    return PairDecision(
        work_a=a,
        work_b=b,
        decision=SAME if verdict == SAME else DIFFERENT,
        score=0.9,
        note="",
        reviewer=reviewer,
        decided_at="2026-10-01T00:00:00Z",
    )


def _log(*decisions: PairDecision) -> list[LoggedDecision]:
    log, prev = [], GENESIS
    for decision in decisions:
        entry = decision.entry()
        hashed = entry_hash(prev, entry)
        log.append(
            LoggedDecision(decision=decision, entry=entry, prev_hash=prev, entry_hash=hashed)
        )
        prev = hashed
    return log


def test_a_score_is_the_best_title_match_and_a_floor_skips_the_rest() -> None:
    """Identical titles score 1; a work's other titles count; below the floor is 0."""
    assert score(["cross modal distillation"], ["cross modal distillation"]) == 1.0
    assert (
        score(["something else", "cross modal distillation"], ["cross modal distillation"]) == 1.0
    )
    low = score(["cross modal distillation"], ["prognosis network for fusion"])
    assert 0 < low < 0.5
    assert score(["cross modal distillation"], ["prognosis network for fusion"], floor=0.8) == 0.0


def test_candidates_leave_out_decided_pairs_and_grouped_works() -> None:
    """Highest score first; a decided pair or two works of one group are not proposed again."""
    facts = {
        "a": _facts("a", "cross modal distillation for tumours"),
        "b": _facts("b", "cross modal distillation for tumors"),
        "c": _facts("c", "cross modal distillation for tumours"),
        "d": _facts("d", "an unrelated title entirely"),
    }
    alone = {work_id: work_id for work_id in facts}
    found = candidate_pairs(facts, alone, set(), 0.8)
    assert [(pair.work_a, pair.work_b) for pair in found] == [("a", "c"), ("a", "b"), ("b", "c")]
    assert found[0].score == 1.0

    joined = {"a": "a", "b": "b", "c": "a", "d": "d"}
    assert [(p.work_a, p.work_b) for p in candidate_pairs(facts, joined, {("a", "b")}, 0.8)] == [
        ("b", "c")
    ]


def test_a_long_title_is_scored_whole() -> None:
    """From 200 characters on, difflib's autojunk would drop common letters; it is off."""
    long = " ".join(["multimodal knowledge distillation for medical image segmentation"] * 4)
    other = long.replace("segmentation", "classification", 1)
    assert len(long) > 200
    assert score([long], [other]) > 0.95
    facts = {"a": _facts("a", long), "b": _facts("b", other)}
    (pair,) = candidate_pairs(facts, {"a": "a", "b": "b"}, set(), 0.8)
    assert pair.score > 0.95


def test_the_fast_listing_agrees_with_scoring_every_pair() -> None:
    """The cheap bounds only skip pairs that cannot reach the threshold: same pairs, same scores."""
    titles = [
        "cross modal distillation for tumour segmentation",
        "cross modal distillation for tumor segmentation",
        "cross modal knowledge distillation for segmentation of tumours",
        "a prognosis network for multimodal fusion",
        "a diagnosis network for multimodal fusion",
        "multimodal fusion network for prognosis",
        "short",
        "shorter",
        "zzzz yyyy xxxx",
    ]
    facts = {f"w{n}": _facts(f"w{n}", title) for n, title in enumerate(titles)}
    alone = {work_id: work_id for work_id in facts}
    for minimum in (0.6, 0.8, 0.95):
        fast = candidate_pairs(facts, alone, set(), minimum)
        slow = sorted(
            (
                (-score(facts[a].titles, facts[b].titles), a, b)
                for index, a in enumerate(facts)
                for b in list(facts)[index + 1 :]
                if score(facts[a].titles, facts[b].titles) >= minimum
            ),
        )
        assert [(-p.score, p.work_a, p.work_b) for p in fast] == slow


def test_same_decisions_join_works_and_the_published_version_names_the_group() -> None:
    """A DOI-named work is kept over an arXiv one, whatever the order they were named in."""
    order = ["preprint2022-aaaaaa", "published2023-bbbbbb", "other2024-cccccc"]
    identities = {
        "preprint2022-aaaaaa": "arxiv:2201.00001",
        "published2023-bbbbbb": "doi:10.0000/x",
        "other2024-cccccc": "doi:10.0000/y",
    }
    decided = current_decisions(
        _log(
            _decision("preprint2022-aaaaaa", "published2023-bbbbbb", SAME),
            _decision("preprint2022-aaaaaa", "other2024-cccccc", DIFFERENT),
        )
    )
    group_of = groups(order, identities, decided)
    assert group_of == {
        "preprint2022-aaaaaa": "published2023-bbbbbb",
        "published2023-bbbbbb": "published2023-bbbbbb",
        "other2024-cccccc": "other2024-cccccc",
    }
    assert contradictions(group_of, decided) == []


def test_a_later_decision_replaces_an_earlier_one() -> None:
    """A correction is a new entry; the latest is the one in force."""
    decided = current_decisions(_log(_decision("a", "b", SAME), _decision("b", "a", DIFFERENT)))
    assert decided[("a", "b")].decision == DIFFERENT
    assert groups(["a", "b"], {}, decided) == {"a": "a", "b": "b"}


def test_a_different_inside_a_group_is_a_contradiction() -> None:
    """Same for a and b, same for b and c: deciding a and c different contradicts that."""
    decided = current_decisions(
        _log(_decision("a", "b", SAME), _decision("b", "c", SAME), _decision("a", "c", DIFFERENT))
    )
    group_of = groups(["a", "b", "c"], {}, decided)
    assert contradictions(group_of, decided) == [
        "a and c are decided different, but same decisions join them"
    ]


def test_the_decisions_chain_names_an_edit() -> None:
    """The chain is the one runs use: an edited entry no longer matches its hash."""
    log = _log(_decision("a", "b", SAME), _decision("c", "d", DIFFERENT))
    assert decision_chain_problems(log) == []
    edited = log[0].entry.replace('"same"', '"different"')
    log[0] = LoggedDecision(
        decision=PairDecision.model_validate_json(edited),
        entry=edited,
        prev_hash=log[0].prev_hash,
        entry_hash=log[0].entry_hash,
    )
    assert decision_chain_problems(log) == [
        "decision 1 (a / b): its content does not match its hash"
    ]
    assert decision_chain_problems([log[1]]) == [
        "decision 1 (c / d): does not follow the entry before it"
    ]
    padded = log[1].entry.replace('"note":""', '"note": ""')
    log[1] = LoggedDecision(
        decision=log[1].decision,
        entry=padded,
        prev_hash=log[1].prev_hash,
        entry_hash=entry_hash(log[1].prev_hash, padded),
    )
    assert "decision 2 (c / d): its entry is not in canonical form" in decision_chain_problems(log)


def test_the_pairs_file_opens_in_a_spreadsheet_safely() -> None:
    """UTF-8 with a mark, the fixed columns, and a title that looks like a formula escaped."""
    facts = {
        "a": _facts("a", '=HYPERLINK("http://x")', doi="10.0000/a"),
        "b": _facts("b", "Ünïcode title"),
    }
    data = write_pairs([candidate_pairs(facts, {"a": "a", "b": "b"}, set(), 0.0)[0]], facts)
    assert data.startswith(b"\xef\xbb\xbf")
    header, row = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert tuple(header) == FIELDS
    assert row[5] == '\'=HYPERLINK("http://x")'
    assert row[6] == "Ünïcode title"
    assert safe_cell("-1") == "'-1"
    assert safe_cell("plain") == "plain"


def _filled(rows: list[tuple[str, str, str, str]], delimiter: str = ",") -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(FIELDS)
    for first, second, decision, note in rows:
        writer.writerow([first, second, "0,95", decision, note, "Título", "Title", *[""] * 8])
    return buffer.getvalue()


def test_a_filled_file_is_read_as_a_spreadsheet_saves_it() -> None:
    """UTF-8 or Windows-1252, commas or semicolons; case ignored; empty rows stay pending."""
    rows = [("a", "b", "SAME", "same paper"), ("c", "d", "", ""), ("", "", "", "")]
    for data in (
        ("﻿" + _filled(rows)).encode("utf-8"),
        _filled(rows, ";").encode("cp1252"),
    ):
        read = read_pairs(data, "pairs.csv")
        assert [(r.line, r.work_a, r.decision, r.note) for r in read] == [
            (2, "a", SAME, "same paper"),
            (3, "c", None, ""),
        ]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_filled([("a", "b", "maybe", "")]).encode(), "line 2 of pairs.csv: the decision 'maybe'"),
        (b"work_a,work_b\na,b\n", "pairs.csv has no column decision"),
        (b"\x81\x8d\x8f\x90\x9d", "is neither UTF-8 nor Windows-1252"),
    ],
    ids=["unknown-decision", "missing-column", "unreadable"],
)
def test_a_file_that_cannot_be_trusted_is_refused(data: bytes, expected: str) -> None:
    """Nothing is half read: one bad row refuses the whole file."""
    with pytest.raises(ReviewError, match=expected):
        read_pairs(data, "pairs.csv")
