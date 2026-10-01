"""The RIS reader (ADR-0016), against synthetic Scopus and IEEE Xplore exports."""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from lrcc.domain.errors import SourceError
from lrcc.domain.ris import read_ris


def test_a_scopus_export_is_read(fixture_bytes: Callable[[str], bytes]) -> None:
    """Scopus's link carries the EID, which becomes the identifier, as its API gives it."""
    first, second = read_ris(fixture_bytes("scopus_export.ris"), "scopus", "scopus.ris")
    assert first.source == "scopus"
    assert first.source_id == "2-s2.0-90000000001"
    assert first.title == "A synthetic Scopus title"
    assert first.authors == ("Example, A.", "Sample, G.")
    assert first.year == 2020
    assert first.doi == "10.0000/synthetic.scopus.1"
    assert first.abstract == "An invented Scopus abstract."
    assert second.source_id == "2-s2.0-90000000002"
    assert second.doi is None
    assert second.year == 2018


def test_an_ieee_export_is_read(fixture_bytes: Callable[[str], bytes]) -> None:
    """Without an EID the DOI identifies a record; without either, a digest of its fields."""
    data = fixture_bytes("ieee_export.ris")
    first, second = read_ris(data, "ieee", "ieee.ris")
    assert first.source_id == "10.0000/synthetic.ieee.1"
    assert first.authors == ("A. Example", "B. Sample")
    assert first.year == 2020
    assert second.doi is None
    assert second.year == 2019
    assert re.fullmatch(r"ris-[0-9a-f]{16}", second.source_id)
    assert read_ris(data, "ieee", "ieee.ris")[1].source_id == second.source_id
    changed = data.replace(b"Another invented", b"A changed")
    assert read_ris(changed, "ieee", "ieee.ris")[1].source_id != second.source_id


def test_older_tag_names_and_continued_lines() -> None:
    """T1, A1, Y1 and N2 stand in for the usual tags, and an untagged line continues a value."""
    data = (
        b"TY  - JOUR\n"
        b"T1  - An older title tag\n"
        b"A1  - Older, A.\n"
        b"Y1  - 2017/03/01/\n"
        b"N2  - An abstract the exporter\n"
        b"      wrapped onto a second line.\n"
        b"ER  - \n"
    )
    (record,) = read_ris(data, "scopus", "old.ris")
    assert record.title == "An older title tag"
    assert record.authors == ("Older, A.",)
    assert record.year == 2017
    assert record.abstract == "An abstract the exporter wrapped onto a second line."


def test_windows_line_endings_and_a_byte_order_mark(
    fixture_bytes: Callable[[str], bytes],
) -> None:
    """The same file saved on Windows, with a byte-order mark, reads the same."""
    plain = fixture_bytes("scopus_export.ris").replace(b"\r\n", b"\n")
    windows = b"\xef\xbb\xbf" + plain.replace(b"\n", b"\r\n")
    assert read_ris(windows, "scopus", "a.ris") == read_ris(plain, "scopus", "a.ris")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"Authors,Title\nExample A.,A title\n", "export.ris is not a RIS file"),
        (b"AU  - Outside, A.\nTY  - JOUR\nER  -\n", "export.ris is not a RIS file"),
        (b"TY  - JOUR\nTI  - a\nTY  - JOUR\nER  -\n", "starts a record inside another"),
        (b"TY  - JOUR\nTI  - cut short\n", "export.ris ends inside a record"),
        (b"\n\n", "export.ris holds no RIS record"),
        (b"TY  - JOUR\nTI  - caf\xe9\nER  -\n", "export.ris is not UTF-8 text"),
    ],
    ids=["csv", "outside-a-record", "nested", "cut-short", "empty", "not-utf8"],
)
def test_a_broken_file_is_refused_not_half_read(data: bytes, expected: str) -> None:
    """Each way a file can fail is named with the file, and no record is returned."""
    with pytest.raises(SourceError, match=expected):
        read_ris(data, "scopus", "export.ris")
