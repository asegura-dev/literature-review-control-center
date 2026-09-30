"""RIS, the tagged format databases export records in (ADR-0016).

An export is a sequence of records. Each record runs from a ``TY`` line to an ``ER`` line, with
one ``TAG  - value`` per line; a line without a tag continues the value before it. LRCC reads the
tags Scopus and IEEE Xplore write for what a record needs: title, authors, year, DOI and
abstract. Every other tag stays in the stored file, unread.

The file comes from outside, so it is data, never instructions. It is refused rather than half
read: a file that is not UTF-8, text outside a record, a record inside another, a file that ends
inside a record, or one with no record at all.
"""

from __future__ import annotations

import hashlib
import re

from lrcc.domain.errors import SourceError
from lrcc.domain.record import Record

_TAGGED = re.compile(r"([A-Z][A-Z0-9])  -(?: (.*))?")
_YEAR = re.compile(r"\d{4}")
#: Scopus writes each record's link with its EID, the identifier its API gives the same record.
_EID = re.compile(r"[?&]eid=([0-9A-Za-z.-]+)")

#: One record's fields, as ``(tag, value)`` pairs in the file's order.
_Fields = list[tuple[str, str]]


def read_ris(data: bytes, source: str, name: str) -> tuple[Record, ...]:
    """Read the records of one RIS file.

    Args:
        data: The file's bytes, exactly as exported. A UTF-8 byte-order mark is accepted.
        source: The source the records came from, such as ``scopus``.
        name: What to call the file in an error, such as its name.

    Returns:
        The records, in the file's order.

    Raises:
        SourceError: If the file is not UTF-8, is not RIS, ends inside a record, or holds none.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as problem:
        raise SourceError(
            f"{name} is not UTF-8 text",
            [f"byte {problem.start}: {problem.reason}", "export it again as RIS, in UTF-8"],
        ) from None
    return tuple(_record(fields, source) for fields in _split(text, name))


def _split(text: str, name: str) -> list[_Fields]:
    records: list[_Fields] = []
    current: _Fields | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        tagged = _TAGGED.fullmatch(line.rstrip())
        if tagged is None:
            if current is None:
                raise SourceError(
                    f"{name} is not a RIS file",
                    [f"line {number} is not a tagged line, such as 'TY  - JOUR'"],
                )
            tag, value = current[-1]
            current[-1] = (tag, f"{value} {line.strip()}".strip())
            continue
        tag, value = tagged.group(1), (tagged.group(2) or "").strip()
        if tag == "TY":
            if current is not None:
                raise SourceError(
                    f"{name} starts a record inside another",
                    [f"line {number}: the record before it has no 'ER' line"],
                )
            current = [(tag, value)]
        elif current is None:
            raise SourceError(
                f"{name} is not a RIS file",
                [f"line {number} lies outside a record, and records start with 'TY  - '"],
            )
        elif tag == "ER":
            records.append(current)
            current = None
        else:
            current.append((tag, value))
    if current is not None:
        raise SourceError(
            f"{name} ends inside a record", ["the file may have been cut short; export it again"]
        )
    if not records:
        raise SourceError(
            f"{name} holds no RIS record", ["a RIS record starts with a line such as 'TY  - JOUR'"]
        )
    return records


def _record(fields: _Fields, source: str) -> Record:
    doi = _first(fields, "DO").lower() or None
    year = _YEAR.search(_first(fields, "PY", "Y1", "DA"))
    return Record(
        source=source,
        source_id=_identifier(fields, doi),
        title=_first(fields, "TI", "T1"),
        authors=tuple(_values(fields, "AU", "A1")),
        year=int(year.group()) if year else None,
        doi=doi,
        abstract=" ".join(_values(fields, "AB", "N2")) or None,
    )


def _values(fields: _Fields, *tags: str) -> list[str]:
    # The first tag that holds a value wins: exporters write the same field under older names.
    for tag in tags:
        found = [value for key, value in fields if key == tag and value]
        if found:
            return found
    return []


def _first(fields: _Fields, *tags: str) -> str:
    found = _values(fields, *tags)
    return found[0] if found else ""


def _identifier(fields: _Fields, doi: str | None) -> str:
    for link in _values(fields, "UR"):
        eid = _EID.search(link)
        if eid:
            return eid.group(1)
    if doi:
        return doi
    # Neither: a digest of the record's own fields, which a replay of the same file derives again.
    lines = "\n".join(f"{tag}  - {value}" for tag, value in fields)
    return "ris-" + hashlib.sha256(lines.encode()).hexdigest()[:16]
