"""Works, their names and the exact linking of records (ADR-0006, ADR-0017)."""

from __future__ import annotations

import hashlib

import pytest

from lrcc.domain.errors import DedupeError
from lrcc.domain.record import Record
from lrcc.domain.works import (
    NEW,
    family_name,
    identifiers_of,
    link_records,
    normalize_doi,
    normalize_title,
    work_id_for,
)


def _record(
    source: str = "ieee",
    source_id: str = "1",
    *,
    title: str = "A synthetic title",
    authors: tuple[str, ...] = ("Ada Example",),
    year: int | None = 2020,
    doi: str | None = None,
) -> Record:
    return Record(
        source=source,
        source_id=source_id,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        abstract=None,
    )


def _hash(identity: str) -> str:
    return hashlib.sha256(identity.encode()).hexdigest()[:6]


def _name(record: Record) -> str:
    (work,) = link_records([("0001-run", 1, record)], {}).works
    return work.work_id


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_record(doi="10.0000/X"), f"example2020-{_hash('doi:10.0000/x')}"),
        (
            _record("pubmed", "90000001", authors=("Example, Ada",)),
            f"example2020-{_hash('pmid:90000001')}",
        ),
        (_record("arxiv", "9912.00001v3"), f"example2020-{_hash('arxiv:9912.00001')}"),
        (
            _record(title="A Title, with: Punctuation!", year=None),
            f"examplend-{_hash('title:a title with punctuation|nd')}",
        ),
        (_record(authors=(), doi="10.0000/x"), f"anon2020-{_hash('doi:10.0000/x')}"),
        (
            _record(authors=("Jörg Müller",), doi="10.0000/x"),
            f"muller2020-{_hash('doi:10.0000/x')}",
        ),
        (
            _record(authors=("Ødegaard, K.",), doi="10.0000/x"),
            f"degaard2020-{_hash('doi:10.0000/x')}",
        ),
        (_record(year=None, doi="10.0000/x"), f"examplend-{_hash('doi:10.0000/x')}"),
        (
            _record(authors=("Averyveryverylongfamilyname, A.",), doi="10.0000/x"),
            f"averyveryverylongfam2020-{_hash('doi:10.0000/x')}",
        ),
    ],
    ids=[
        "doi",
        "pmid",
        "arxiv-version",
        "no-identifier",
        "no-author",
        "non-ascii",
        "letter-dropped",
        "no-year",
        "long-name",
    ],
)
def test_a_work_is_named_as_adr_0006_says(record: Record, expected: str) -> None:
    """Family name, year and the hash of the first identifier by precedence."""
    assert _name(record) == expected


@pytest.mark.parametrize(
    ("author", "family"),
    [
        ("Dou, Qi", "Dou"),
        ("Dou Q.", "Dou"),
        ("Van der Berg JH", "Van der Berg"),
        ("Qi Dou", "Dou"),
        ("A. Example", "Example"),
        ("Consortium", "Consortium"),
        ("   ", ""),
    ],
)
def test_the_family_name_reads_every_source_convention(author: str, family: str) -> None:
    """PubMed, Scopus, IEEE Xplore, arXiv and RIS write authors differently."""
    assert family_name(author) == family


def test_identifiers_follow_their_precedence() -> None:
    """The DOI first, the source's own identifier next, the title only when nothing is stable."""
    assert identifiers_of(_record("pubmed", "90000001", doi="https://doi.org/10.0000/A")) == (
        "doi:10.0000/a",
        "pmid:90000001",
    )
    assert identifiers_of(_record("arxiv", "9912.00001v2")) == ("arxiv:9912.00001",)
    assert identifiers_of(_record("ieee", "123", doi="10.0000/a")) == ("doi:10.0000/a", "ieee:123")
    assert identifiers_of(_record("scopus", "10.0000/a", doi="10.0000/a")) == ("doi:10.0000/a",)
    assert identifiers_of(_record("ieee", "123")) == ("ieee:123", "title:a synthetic title|2020")
    assert identifiers_of(_record("pubmed", "ris-0f0f")) == (
        "pubmed:ris-0f0f",
        "title:a synthetic title|2020",
    )
    # Imported as arXiv, an identifier of another shape is never taken for an arXiv one.
    assert identifiers_of(_record("arxiv", "ris-0f0f")) == (
        "arxiv-record:ris-0f0f",
        "title:a synthetic title|2020",
    )


def test_normalization() -> None:
    """Titles fold accents, case and punctuation; DOIs lose case and resolver."""
    assert normalize_title("Ünïcode — Title: Part 2") == "unicode title part 2"
    assert normalize_doi(" HTTPS://DX.DOI.ORG/10.0000/AbC ") == "10.0000/abc"
    assert normalize_doi("  ") is None
    assert work_id_for(_record(), "doi:10.0000/x") == f"example2020-{_hash('doi:10.0000/x')}"


def test_records_of_two_sources_join_through_a_doi() -> None:
    """The second record joins, and its PMID becomes an alias of the work."""
    ieee = _record("ieee", "123", doi="10.0000/a")
    pubmed = _record("pubmed", "90000001", doi="10.0000/A", authors=("Example, Ada",))
    linked = link_records([("0001-ieee", 1, ieee), ("0002-pubmed", 1, pubmed)], {})
    (work,) = linked.works
    assert [link.matched_by for link in linked.links] == [NEW, "doi:10.0000/a"]
    assert {link.work_id for link in linked.links} == {work.work_id}
    assert linked.aliases == {
        "doi:10.0000/a": work.work_id,
        "ieee:123": work.work_id,
        "pmid:90000001": work.work_id,
    }
    assert not work.unstable


def test_a_later_pass_joins_works_already_known() -> None:
    """With the catalog's identifiers, a new record creates nothing."""
    first = link_records([("0001-ieee", 1, _record(doi="10.0000/a"))], {})
    later = link_records(
        [("0002-pubmed", 1, _record("pubmed", "7", doi="10.0000/a"))], first.aliases
    )
    assert later.works == ()
    assert later.links[0].work_id == first.works[0].work_id
    assert later.aliases == {"pmid:7": first.works[0].work_id}


def test_records_without_identifiers_join_on_title_and_year_only() -> None:
    """Two records with no DOI share a title identity; a record with a DOI never uses it."""
    ieee = _record("ieee", "1", title="Same Title")
    scopus = _record("scopus", "2-s2.0-1", title="same title")
    with_doi = _record("pubmed", "5", title="Same Title", doi="10.0000/z")
    linked = link_records([("r1", 1, ieee), ("r2", 1, scopus), ("r3", 1, with_doi)], {})
    first, second = linked.works
    assert first.unstable and not second.unstable
    assert [link.matched_by for link in linked.links] == [NEW, "title:same title|2020", NEW]


def test_a_record_with_no_title_is_named_from_the_database_s_own_identifier() -> None:
    """The last resort of ADR-0017: no DOI, PMID, arXiv id or title, but the source's number."""
    record = _record("ieee", "123", title="")
    assert identifiers_of(record) == ("ieee:123",)
    (work,) = link_records([("r1", 1, record)], {}).works
    assert work.work_id == f"example2020-{_hash('ieee:123')}"
    assert work.unstable


def test_identifiers_of_two_works_are_refused() -> None:
    """A record that would merge two named works stops the pass: nothing is returned."""
    known = {"doi:10.0000/a": "one2020-aaaaaa", "pmid:5": "two2020-bbbbbb"}
    with pytest.raises(DedupeError, match="carries identifiers of two works") as caught:
        link_records([("r9", 3, _record("pubmed", "5", doi="10.0000/a"))], known)
    assert "one2020-aaaaaa, two2020-bbbbbb" in caught.value.message


def test_a_name_already_taken_is_refused() -> None:
    """A collision is never suffixed: a person decides (ADR-0006)."""
    record = _record(doi="10.0000/x")
    known = {"doi:10.0000/other": _name(record)}
    with pytest.raises(DedupeError, match="would name two works"):
        link_records([("r1", 1, record)], known)


def test_linking_is_deterministic() -> None:
    """The same records in the same order give the same works, names and reasons."""
    items = [("r1", n, _record("ieee", str(n), title=f"Title {n % 3}")) for n in range(1, 10)]
    assert link_records(items, {}) == link_records(items, {})
