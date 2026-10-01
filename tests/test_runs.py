"""Runs and the hash chain of the run log (ADR-0012): what is recorded, and what breaks a chain."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from lrcc.domain.record import RawResponse, Record, SearchResult
from lrcc.domain.runs import (
    GENESIS,
    Imported,
    LoggedRun,
    Run,
    build_run,
    chain_problems,
    entry_hash,
    records_digest,
)

STARTED = datetime(2026, 9, 30, 14, 15, 0, tzinfo=UTC)
FINISHED = datetime(2026, 9, 30, 14, 15, 7, tzinfo=UTC)


def _result(reported: int = 2) -> SearchResult:
    records = tuple(
        Record(
            source="arxiv",
            source_id=f"9912.0000{number}",
            title=f"Synthetic title {number}",
            authors=("Ada Example",),
            year=2023,
            doi=None,
            abstract=None,
        )
        for number in (1, 2)
    )
    responses = (RawResponse(url="https://export.arxiv.org/api/query?start=0", body=b"<feed/>"),)
    return SearchResult(
        source="arxiv", query="abs:a", reported=reported, records=records, responses=responses
    )


def _run(sequence: int = 1, reported: int = 2) -> Run:
    return build_run(
        sequence=sequence,
        started=STARTED,
        finished=FINISHED,
        protocol_sha256="p" * 64,
        result=_result(reported),
        lrcc_version="0.5.0",
    )


def _log(*runs: Run) -> list[LoggedRun]:
    log = []
    prev = GENESIS
    for run in runs:
        entry = run.entry()
        hashed = entry_hash(prev, entry)
        log.append(LoggedRun(run=run, entry=entry, prev_hash=prev, entry_hash=hashed))
        prev = hashed
    return log


def test_a_run_records_what_was_asked_and_what_came_back() -> None:
    """Identifier, times, digests and counts all come from the search itself."""
    run = _run()
    assert run.run_id == "0001-20260930T141500Z-arxiv"
    assert run.started_at == "2026-09-30T14:15:00Z"
    assert run.finished_at == "2026-09-30T14:15:07Z"
    assert run.query_sha256 == hashlib.sha256(b"abs:a").hexdigest()
    assert run.retrieved == 2
    (response,) = run.responses
    assert response.file == "response-0001.raw"
    assert response.size == len(b"<feed/>")
    assert response.sha256 == hashlib.sha256(b"<feed/>").hexdigest()


def test_a_run_that_retrieved_less_than_reported_is_incomplete() -> None:
    """A truncated retrieval never looks complete."""
    assert _run(reported=2).complete
    assert not _run(reported=57).complete


def test_the_entry_is_canonical_json() -> None:
    """Sorted keys and no spare whitespace: the same run always hashes the same."""
    entry = _run().entry()
    assert json.loads(entry)["run_id"] == "0001-20260930T141500Z-arxiv"
    assert entry == json.dumps(json.loads(entry), sort_keys=True, separators=(",", ":"))


def test_an_entry_written_before_imports_keeps_its_form() -> None:
    """A search's entry has no ``imported`` key, so a log written by v0.7.0 still verifies."""
    search = _run()
    entry = search.entry()
    assert "imported" not in json.loads(entry)
    assert Run.model_validate_json(entry).entry() == entry
    assert search.searched_on == "2026-09-30"

    imported = build_run(
        sequence=2,
        started=STARTED,
        finished=FINISHED,
        protocol_sha256="p" * 64,
        result=_result(),
        lrcc_version="0.8.0",
        imported=Imported(format="ris", searched_on="2026-09-28"),
    )
    assert json.loads(imported.entry())["imported"] == {
        "format": "ris",
        "searched_on": "2026-09-28",
    }
    assert imported.searched_on == "2026-09-28"
    assert chain_problems(_log(search, imported)) == []

    # Writing the empty field out would be another form of the same run, and is caught.
    padded = json.dumps(
        {**json.loads(entry), "imported": None}, sort_keys=True, separators=(",", ":")
    )
    logged = LoggedRun(
        run=Run.model_validate_json(padded),
        entry=padded,
        prev_hash=GENESIS,
        entry_hash=entry_hash(GENESIS, padded),
    )
    assert chain_problems([logged]) == [
        "0001-20260930T141500Z-arxiv: its entry is not in canonical form"
    ]


def test_the_records_digest_depends_on_content_and_order() -> None:
    """A replay that derives the same records, in the same order, gets the same digest."""
    first, second = _result().records
    assert records_digest([first, second]) == records_digest([first, second])
    assert records_digest([first, second]) != records_digest([second, first])


def test_an_untouched_chain_has_no_problems() -> None:
    """Each entry's hash covers the entry and the hash before it."""
    assert chain_problems(_log(_run(1), _run(2), _run(3))) == []
    assert chain_problems([]) == []


def test_an_edited_entry_breaks_the_chain() -> None:
    """Changing a count in the stored entry no longer matches its hash."""
    log = _log(_run(1), _run(2))
    edited = log[0].entry.replace('"reported":2', '"reported":9')
    log[0] = LoggedRun(
        run=Run.model_validate_json(edited),
        entry=edited,
        prev_hash=log[0].prev_hash,
        entry_hash=log[0].entry_hash,
    )
    assert chain_problems(log) == [
        "0001-20260930T141500Z-arxiv: its content does not match its hash"
    ]


def test_a_removed_entry_breaks_the_chain() -> None:
    """The entry after a removed one no longer follows its predecessor."""
    log = _log(_run(1), _run(2), _run(3))
    del log[1]
    assert chain_problems(log) == [
        "0003-20260930T141500Z-arxiv: does not follow the entry before it"
    ]


def test_reordered_entries_break_the_chain() -> None:
    """Swapping two entries is caught at both."""
    log = _log(_run(1), _run(2))
    problems = chain_problems([log[1], log[0]])
    assert len(problems) == 2
