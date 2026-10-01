"""The workspace's work catalog in DuckDB: ``library/catalog.duckdb`` (ADR-0006, ADR-0017).

Two tables: ``works``, each ``work_id`` with the identifier it was named from and when, and
``identifiers``, each typed identifier with its work. The identifier is the primary key, so
"one identifier, one work" is a property of the database, not of the code that writes to it.
The catalog holds identity only; links, states and decisions stay in each review's database.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import duckdb

from lrcc.domain.errors import StoreError
from lrcc.domain.works import Work

CATALOG = "catalog.duckdb"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS works (
        seq INTEGER PRIMARY KEY,
        work_id VARCHAR NOT NULL UNIQUE,
        identity VARCHAR NOT NULL,
        unstable BOOLEAN NOT NULL,
        assigned_at VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS identifiers (
        identifier VARCHAR PRIMARY KEY,
        work_id VARCHAR NOT NULL
    )
    """,
)


class DuckDbWorkCatalog:
    """The DuckDB implementation of the catalog port."""

    def __init__(self, path: Path) -> None:
        """Create the catalog. Nothing is opened or written until a method is called.

        Args:
            path: ``library/catalog.duckdb`` inside the workspace, already resolved.
        """
        self._path = path

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        try:
            self._path.parent.mkdir(exist_ok=True)
            connection = duckdb.connect(str(self._path))
        except (OSError, duckdb.Error) as problem:
            raise StoreError(
                f"cannot open {self._path}",
                [str(problem), "another lrcc command may be using the catalog"],
            ) from None
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
            yield connection
        except duckdb.Error as problem:
            raise StoreError(f"cannot use {self._path}", [str(problem)]) from None
        finally:
            connection.close()

    def identifiers(self) -> dict[str, str]:
        """Return every known identifier with its work; empty, and nothing created, if none."""
        if not self._path.exists():
            return {}
        with self._connection() as connection:
            rows = connection.execute("SELECT identifier, work_id FROM identifiers").fetchall()
        return {identifier: work_id for identifier, work_id in rows}

    def works(self) -> dict[str, Work]:
        """Return every work by ``work_id``; empty, and nothing created, if none."""
        if not self._path.exists():
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT work_id, identity, unstable FROM works ORDER BY seq"
            ).fetchall()
        return {
            work_id: Work(work_id=work_id, identity=identity, unstable=unstable)
            for work_id, identity, unstable in rows
        }

    def add(self, works: Sequence[Work], aliases: Mapping[str, str], assigned_at: str) -> None:
        """Add new works and identifiers in one transaction; an identifier taken is refused.

        Args:
            works: The works to create.
            aliases: The new identifiers, each with its work.
            assigned_at: When the works were named, in UTC.

        Raises:
            StoreError: If the catalog cannot be written, or an identifier or ``work_id`` is
                already taken. Nothing is written in that case.
        """
        if not works and not aliases:
            return
        with self._connection() as connection:
            connection.begin()
            row = connection.execute("SELECT coalesce(max(seq), 0) FROM works").fetchone()
            seq = row[0] if row else 0
            try:
                for offset, work in enumerate(works, start=1):
                    connection.execute(
                        "INSERT INTO works VALUES (?, ?, ?, ?, ?)",
                        [seq + offset, work.work_id, work.identity, work.unstable, assigned_at],
                    )
                for identifier, work_id in aliases.items():
                    connection.execute(
                        "INSERT INTO identifiers VALUES (?, ?)", [identifier, work_id]
                    )
            except duckdb.ConstraintException as problem:
                connection.rollback()
                raise StoreError(
                    f"the catalog {self._path} refused a work or an identifier already taken",
                    [str(problem), "one identifier names one work (ADR-0006)"],
                ) from None
            connection.commit()
