"""Candidate pairs as a CSV file a person fills in a spreadsheet, and read back (ADR-0018).

LRCC writes UTF-8 with a byte-order mark, so a spreadsheet opens accents correctly. A cell that
begins like a formula is escaped with a leading ``'``, so a title cannot run as one.

Reading is strict about what matters and lenient about what a spreadsheet changes: UTF-8 or
Windows-1252, commas or semicolons. Only the two ``work_id``s, the decision and the note are read;
an unknown decision refuses the whole file. The file came from outside, so it is data, never
instructions.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lrcc.domain.errors import ReviewError
from lrcc.domain.fuzzy import DIFFERENT, SAME, Candidate, Verdict, WorkFacts

#: The columns, in order. The person fills ``decision`` and, if they wish, ``note``.
FIELDS = (
    "work_a",
    "work_b",
    "score",
    "decision",
    "note",
    "title_a",
    "title_b",
    "first_author_a",
    "first_author_b",
    "year_a",
    "year_b",
    "sources_a",
    "sources_b",
    "doi_a",
    "doi_b",
)
_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_READ = ("work_a", "work_b", "decision")


@dataclass(frozen=True)
class RowDecision:
    """One filled row: its line in the file, the two works, and the decision, or None if empty."""

    line: int
    work_a: str
    work_b: str
    decision: Verdict | None
    note: str


def safe_cell(value: str) -> str:
    """Escape a cell that a spreadsheet would read as a formula.

    Args:
        value: The cell's text.

    Returns:
        The text, with a leading ``'`` if it begins with ``=``, ``+``, ``-``, ``@``, a tab or a
        carriage return.
    """
    return f"'{value}" if value.startswith(_FORMULA) else value


def write_pairs(candidates: Sequence[Candidate], facts: Mapping[str, WorkFacts]) -> bytes:
    """Return the candidate pairs as a CSV file's bytes.

    Args:
        candidates: The pairs, in the order to list them.
        facts: Every work of the review.

    Returns:
        UTF-8 with a byte-order mark, comma-separated, one row per pair.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    for candidate in candidates:
        first, second = facts[candidate.work_a], facts[candidate.work_b]
        row = (
            first.work_id,
            second.work_id,
            f"{candidate.score:.3f}",
            "",
            "",
            first.title,
            second.title,
            first.first_author,
            second.first_author,
            str(first.year or ""),
            str(second.year or ""),
            " ".join(first.sources),
            " ".join(second.sources),
            first.doi or "",
            second.doi or "",
        )
        writer.writerow([safe_cell(cell) for cell in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        raise ReviewError(
            f"{name} is neither UTF-8 nor Windows-1252 text",
            ["save it from the spreadsheet as CSV"],
        ) from None


def read_pairs(data: bytes, name: str) -> list[RowDecision]:
    """Read the filled rows of a candidate-pairs file.

    Args:
        data: The file's bytes, as the spreadsheet saved them.
        name: What to call the file in an error.

    Returns:
        Every row that names two works, with its decision or None when left empty.

    Raises:
        ReviewError: If the file cannot be decoded, lacks a column LRCC reads, or holds a
            decision other than ``same``, ``different`` or nothing.
    """
    text = _decode(data, name)
    header = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if header.count(";") > header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    missing = [column for column in _READ if column not in (reader.fieldnames or [])]
    if missing:
        raise ReviewError(
            f"{name} has no column {', '.join(missing)}",
            ["write the file with: lrcc candidates REVIEW_ID --csv FILE"],
        )
    rows = []
    for line, row in enumerate(reader, start=2):
        first = (row.get("work_a") or "").strip()
        second = (row.get("work_b") or "").strip()
        verdict = (row.get("decision") or "").strip().lower()
        if not (first or second or verdict):
            continue
        if verdict not in ("", SAME, DIFFERENT):
            raise ReviewError(
                f"line {line} of {name}: the decision {verdict!r} is neither same nor different",
                ["leave it empty to decide later; nothing was recorded"],
            )
        decision: Verdict | None = SAME if verdict == SAME else DIFFERENT if verdict else None
        rows.append(RowDecision(line, first, second, decision, (row.get("note") or "").strip()))
    return rows
