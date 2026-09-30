"""The source port: what a feature needs from a bibliographic database (ADR-0011).

It is shaped by its two real implementations, PubMed and arXiv: a search string and a limit go
in, and the count the source reported comes out with the records retrieved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from lrcc.domain.gold import GoldWork
from lrcc.domain.record import Record, SearchResult


class Source(Protocol):
    """A bibliographic database that can run a search string."""

    @property
    def name(self) -> str:
        """The source's name, as protocols write it under ``sources``."""
        ...

    def search(self, query: str, limit: int) -> SearchResult:
        """Run ``query`` and return at most ``limit`` records.

        Args:
            query: The search string, in the source's own syntax.
            limit: The most records to retrieve.

        Returns:
            The count the source reported for the query, and the records retrieved.
        """
        ...

    def records_from(self, bodies: Sequence[bytes]) -> tuple[Record, ...]:
        """Derive the records from the raw answers of one search, without any request.

        Args:
            bodies: The answers exactly as received, in the order they were asked for.

        Returns:
            The records, as a search that received those answers derives them.
        """
        ...

    def holds(self, work: GoldWork, query: str | None) -> bool | None:
        """Say whether the source holds ``work``, and whether ``query`` retrieves it.

        Args:
            work: A work from a gold set.
            query: A search string, or None to ask only whether the source indexes the work.

        Returns:
            True or False, or None if the work has no identifier this source can look up.
        """
        ...
