"""The source port: what a feature needs from a bibliographic database (ADR-0011).

It is shaped by its two real implementations, PubMed and arXiv: a search string and a limit go
in, and the count the source reported comes out with the records retrieved.
"""

from __future__ import annotations

from typing import Protocol

from lrcc.domain.record import SearchResult


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
