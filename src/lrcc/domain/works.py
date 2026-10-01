"""Works, how records join them, and how a work is named (ADR-0006, ADR-0017).

A record is one hit from one source; a work is one publication. Records join works through
shared typed identifiers: a DOI, a PMID, an arXiv identifier, or a database's own identifier for
the record. A record with none of the first three also carries its normalized title and year,
the identity ADR-0006 gives such a work. A work's ``work_id`` is computed once, from the first
record seen, and never again; every identifier met later becomes an alias.

Everything here is pure. The same records, in the same order, with the same identifiers already
known, give the same works.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from lrcc.domain.errors import DedupeError
from lrcc.domain.record import Record

#: What a link records as its reason when the record started a new work.
NEW = "new"

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_PMID = re.compile(r"[1-9][0-9]{0,9}")
_ARXIV = re.compile(r"\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Za-z-]+)?/\d{7}")
_VERSION = re.compile(r"v\d+$")
#: Trailing initials after a family name, as in ``Dou Q.`` or ``Smith JH``.
_INITIALS = re.compile(r"(?:[A-Z]\.?){1,3}")
#: The types whose hash gives a work a stable identity, in order of precedence (ADR-0006).
_STABLE = ("doi", "pmid", "arxiv")


class Work(BaseModel):
    """A work as the catalog knows it: its name, and the identifier it was named from.

    ``unstable`` marks a work named from a title or a database's own number, not from a DOI, a
    PMID or an arXiv identifier (ADR-0006).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_id: str
    identity: str
    unstable: bool


class Link(BaseModel):
    """One record joined to its work, and the identifier that joined it, or ``new``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    position: int
    work_id: str
    matched_by: str


@dataclass(frozen=True)
class Linked:
    """What one pass adds: the works it created, the aliases it learned, the links it made."""

    works: tuple[Work, ...]
    aliases: dict[str, str]
    links: tuple[Link, ...]


def normalize_doi(value: str | None) -> str | None:
    """Return a DOI lowercased, without a resolver prefix, or None if there is none.

    Args:
        value: A DOI as a source gave it.

    Returns:
        The normalized DOI, or None for a missing or empty one.
    """
    text = (value or "").strip().lower()
    for prefix in _DOI_PREFIXES:
        text = text.removeprefix(prefix)
    return text or None


def normalize_title(value: str) -> str:
    """Fold a title for comparison: NFKD, lowercase, and every run of other characters one space.

    Args:
        value: A title as a source gave it.

    Returns:
        Lowercase ASCII letters and digits separated by single spaces; empty if none remain.
    """
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


def family_name(author: str) -> str:
    """Take the family name out of an author string, whatever the source's convention.

    ``Family, Given`` gives the part before the comma; ``Family GH``, with trailing initials,
    gives everything before them; anything else gives the last word.

    Args:
        author: One author as a source wrote it.

    Returns:
        The family name as written, or an empty string.
    """
    name = author.strip()
    if "," in name:
        return name.split(",", 1)[0]
    words = name.split()
    if len(words) > 1 and _INITIALS.fullmatch(words[-1]):
        return " ".join(words[:-1])
    return words[-1] if words else ""


def identifiers_of(record: Record) -> tuple[str, ...]:
    """Return a record's typed, normalized identifiers, in order of precedence.

    Args:
        record: A record from any source.

    Returns:
        ``doi:``, then ``pmid:`` or ``arxiv:`` for those sources' own identifiers, then the
        database's own (``ieee:``, ``scopus:``; ``arxiv-record:`` for an imported arXiv record
        whose identifier is not an arXiv one), then ``title:<title>|<year>`` when the record has
        no DOI, PMID or arXiv identifier.
    """
    found: list[str] = []
    doi = normalize_doi(record.doi)
    if doi:
        found.append(f"doi:{doi}")
    own = record.source_id.strip()
    arxiv = _VERSION.sub("", own)
    if record.source == "pubmed" and _PMID.fullmatch(own):
        found.append(f"pmid:{own}")
    elif record.source == "arxiv" and _ARXIV.fullmatch(arxiv):
        found.append(f"arxiv:{arxiv}")
    elif own and own.lower() != doi:
        # A source named like a stable type (arXiv) marks an identifier of another shape apart,
        # so a RIS digest imported as arXiv is never taken for an arXiv identifier.
        kind = f"{record.source}-record" if record.source in _STABLE else record.source
        found.append(f"{kind}:{own}")
    if not any(identifier.split(":", 1)[0] in _STABLE for identifier in found):
        title = normalize_title(record.title)
        if title:
            found.append(f"title:{title}|{record.year or 'nd'}")
    return tuple(found)


def _identity(identifiers: Sequence[str]) -> tuple[str, bool]:
    for kind in (*_STABLE, "title"):
        for identifier in identifiers:
            if identifier.startswith(f"{kind}:"):
                return identifier, kind == "title"
    return identifiers[0], True


def work_id_for(record: Record, identity: str) -> str:
    """Name a work from its first record and the identifier it is named from (ADR-0006).

    Args:
        record: The first record seen of the work.
        identity: The typed identifier whose hash goes in the name.

    Returns:
        ``<author><year>-<hash6>``: the first author's family name folded to at most 20 ASCII
        letters (``anon`` if none remains), the year (``nd`` if none), and the first six hex
        digits of the identifier's SHA-256.
    """
    family = family_name(record.authors[0]) if record.authors else ""
    folded = unicodedata.normalize("NFKD", family).encode("ascii", "ignore").decode().lower()
    author = re.sub(r"[^a-z]", "", folded)[:20] or "anon"
    year = str(record.year) if record.year else "nd"
    return f"{author}{year}-{hashlib.sha256(identity.encode()).hexdigest()[:6]}"


def link_records(items: Sequence[tuple[str, int, Record]], known: Mapping[str, str]) -> Linked:
    """Join records to works, in order, through the identifiers already known.

    Args:
        items: ``(run_id, position, record)`` for every record not yet linked, in log order.
        known: Every identifier the catalog holds, with the work it belongs to.

    Returns:
        The works created, the aliases learned and one link per record.

    Raises:
        DedupeError: If a record carries identifiers of two different works, or a new work's
            name is already taken. Nothing is returned, so nothing is written.
    """
    known = dict(known)
    taken = set(known.values())
    works: list[Work] = []
    aliases: dict[str, str] = {}
    links: list[Link] = []
    for run_id, position, record in items:
        identifiers = identifiers_of(record)
        owners = sorted({known[identifier] for identifier in identifiers if identifier in known})
        if len(owners) > 1:
            raise DedupeError(
                f"record {position} of run {run_id} carries identifiers of two works:"
                f" {', '.join(owners)}",
                [
                    f"its identifiers: {', '.join(identifiers)}",
                    "merging two works is not built yet (ADR-0017); nothing was linked",
                ],
            )
        if owners:
            work_id = owners[0]
            matched = next(identifier for identifier in identifiers if identifier in known)
        else:
            identity, unstable = _identity(identifiers)
            work_id = work_id_for(record, identity)
            if work_id in taken:
                other = next(name for name, owner in known.items() if owner == work_id)
                raise DedupeError(
                    f"the work_id {work_id} would name two works",
                    [
                        f"already named: the work of {other}",
                        f"new: record {position} of run {run_id}, {identity}",
                        "extending the hash is a person's decision (ADR-0006); nothing was linked",
                    ],
                )
            taken.add(work_id)
            works.append(Work(work_id=work_id, identity=identity, unstable=unstable))
            matched = NEW
        for identifier in identifiers:
            if identifier not in known:
                known[identifier] = work_id
                aliases[identifier] = work_id
        links.append(Link(run_id=run_id, position=position, work_id=work_id, matched_by=matched))
    return Linked(tuple(works), aliases, tuple(links))
