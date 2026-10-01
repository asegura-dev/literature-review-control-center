"""The catalog port: what a feature needs from the workspace's work identity (ADR-0006).

It has one implementation, DuckDB, in ``library/catalog.duckdb``. Like the store port, it exists
because a feature may not import an adapter (ADR-0003); it is a typing seam, not an abstraction
over engines.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from lrcc.domain.works import Work


class WorkCatalog(Protocol):
    """Every work of the workspace and every identifier that names one."""

    def identifiers(self) -> dict[str, str]:
        """Return every known identifier with the work it belongs to.

        Returns:
            The identifiers, empty if the catalog does not exist yet.
        """
        ...

    def works(self) -> dict[str, Work]:
        """Return every work, by ``work_id``.

        Returns:
            The works, empty if the catalog does not exist yet.
        """
        ...

    def add(self, works: Sequence[Work], aliases: Mapping[str, str], assigned_at: str) -> None:
        """Add new works and new identifiers, in one transaction.

        Args:
            works: The works to create.
            aliases: The new identifiers, each with its work.
            assigned_at: When the works were named, in UTC.
        """
        ...
