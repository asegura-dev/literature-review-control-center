"""A review's storage in DuckDB, with its raw responses as files (ADR-0004, ADR-0012).

Besides the run log and the records, the database links each record to its work (ADR-0017).

The database is ``review.duckdb`` in the review's folder. Raw responses are written byte for byte
under ``runs/<run_id>/`` before the log entry that names them, so the log never points at a file
that is not there. Every statement is parameterized. A connection is opened for one operation and
closed, because DuckDB allows one writing process at a time.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import duckdb
from pydantic import ValidationError

from lrcc.domain.errors import StoreError
from lrcc.domain.record import Record, SearchResult
from lrcc.domain.runs import GENESIS, LoggedRun, Run, entry_hash
from lrcc.domain.works import Link

DATABASE = "review.duckdb"
RUNS = "runs"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        seq INTEGER PRIMARY KEY,
        run_id VARCHAR NOT NULL UNIQUE,
        entry VARCHAR NOT NULL,
        prev_hash VARCHAR NOT NULL,
        entry_hash VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS records (
        run_id VARCHAR NOT NULL,
        position INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        source_id VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        authors VARCHAR[] NOT NULL,
        year INTEGER,
        doi VARCHAR,
        abstract VARCHAR,
        PRIMARY KEY (run_id, position)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS links (
        run_id VARCHAR NOT NULL,
        position INTEGER NOT NULL,
        work_id VARCHAR NOT NULL,
        matched_by VARCHAR NOT NULL,
        PRIMARY KEY (run_id, position)
    )
    """,
)


class DuckDbReviewStore:
    """The DuckDB implementation of the store port, for one review."""

    def __init__(self, review_dir: Path) -> None:
        """Create the store. Nothing is opened or written until a method is called.

        Args:
            review_dir: The review's folder, already resolved inside the workspace.
        """
        self._review_dir = review_dir
        self._database = review_dir / DATABASE

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        try:
            connection = duckdb.connect(str(self._database))
        except duckdb.Error as problem:
            raise StoreError(
                f"cannot open {self._database}",
                [str(problem), "another lrcc command may be using this review"],
            ) from None
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
            yield connection
        except duckdb.Error as problem:
            raise StoreError(f"cannot use {self._database}", [str(problem)]) from None
        finally:
            connection.close()

    def head(self) -> tuple[int, str]:
        """Return how many runs the log holds, and the hash of its last entry.

        Returns:
            The count and the last hash, or zero and the genesis hash for an empty log. A review
            with no database yet has an empty log, and none is created by asking.
        """
        log = self.log()
        return (len(log), log[-1].entry_hash) if log else (0, GENESIS)

    def save_run(self, run: Run, result: SearchResult) -> LoggedRun:
        """Append ``run`` to the log, with its records and its raw responses.

        Args:
            run: The run to append.
            result: The search result the run describes.

        Returns:
            The run as logged, with its place in the chain.

        Raises:
            StoreError: If the run's folder already exists, or the files or the database cannot
                be written.
        """
        folder = self._review_dir / RUNS / run.run_id
        try:
            folder.mkdir(parents=True)
            for stored, response in zip(run.responses, result.responses, strict=True):
                (folder / stored.file).write_bytes(response.body)
        except OSError as problem:
            raise StoreError(
                f"cannot store the responses of {run.run_id}", [str(problem)]
            ) from None

        entry = run.entry()
        with self._connection() as connection:
            connection.begin()
            row = connection.execute(
                "SELECT count(*), max_by(entry_hash, seq) FROM runs"
            ).fetchone()
            count, last = (row[0], row[1]) if row else (0, None)
            prev_hash = last or GENESIS
            logged = LoggedRun(
                run=run, entry=entry, prev_hash=prev_hash, entry_hash=entry_hash(prev_hash, entry)
            )
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                [count + 1, run.run_id, entry, prev_hash, logged.entry_hash],
            )
            for position, record in enumerate(result.records, start=1):
                connection.execute(
                    "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        run.run_id,
                        position,
                        record.source,
                        record.source_id,
                        record.title,
                        list(record.authors),
                        record.year,
                        record.doi,
                        record.abstract,
                    ],
                )
            connection.commit()
        return logged

    def log(self) -> tuple[LoggedRun, ...]:
        """Return every logged run, in order.

        Returns:
            The log's entries. Empty if the review has no database yet.
        """
        if not self._database.exists():
            return ()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT entry, prev_hash, entry_hash FROM runs ORDER BY seq"
            ).fetchall()
        try:
            return tuple(
                LoggedRun(
                    run=Run.model_validate_json(entry),
                    entry=entry,
                    prev_hash=prev_hash,
                    entry_hash=hashed,
                )
                for entry, prev_hash, hashed in rows
            )
        except ValidationError as problem:
            raise StoreError(
                f"the run log in {self._database} holds an entry that is not a run",
                [f"{problem.error_count()} field(s) do not fit; the log was edited or damaged"],
            ) from None

    def read_response(self, run_id: str, file: str) -> bytes | None:
        """Return a stored raw response, or None if its file is not there.

        The names come from the log, which may have been edited, so the path is resolved and
        checked to lie inside the runs folder before anything is read.

        Args:
            run_id: The run the response belongs to.
            file: The response's file name, as the log records it.

        Returns:
            The file's bytes, or None.

        Raises:
            StoreError: If the names lead outside the review's runs folder.
        """
        runs = (self._review_dir / RUNS).resolve()
        path = (runs / run_id / file).resolve()
        if not path.is_relative_to(runs):
            raise StoreError(f"the log names a response outside the review: {run_id}/{file}")
        return path.read_bytes() if path.is_file() else None

    def files_on_disk(self) -> dict[str, tuple[str, ...]]:
        """Return what the runs folder really holds: each run folder and the files inside it.

        Returns:
            A mapping from each folder under ``runs/`` to the names of its files, both sorted.
            Empty if the review has no runs folder.
        """
        runs = self._review_dir / RUNS
        if not runs.is_dir():
            return {}
        return {
            folder.name: tuple(sorted(path.name for path in folder.iterdir()))
            for folder in sorted(runs.iterdir())
            if folder.is_dir()
        }

    def records(self, run_id: str) -> tuple[Record, ...]:
        """Return the records the database holds for a run, in order.

        Args:
            run_id: The run whose records to read.

        Returns:
            The records, as stored. Empty if the review has no database yet.
        """
        if not self._database.exists():
            return ()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT source, source_id, title, authors, year, doi, abstract"
                " FROM records WHERE run_id = ? ORDER BY position",
                [run_id],
            ).fetchall()
        return tuple(
            Record(
                source=source,
                source_id=source_id,
                title=title,
                authors=tuple(authors),
                year=year,
                doi=doi,
                abstract=abstract,
            )
            for source, source_id, title, authors, year, doi, abstract in rows
        )

    def links(self) -> tuple[Link, ...]:
        """Return every record's link to its work, in log order (ADR-0017).

        Returns:
            The links. Empty if the review has no database yet.
        """
        if not self._database.exists():
            return ()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT l.run_id, l.position, l.work_id, l.matched_by FROM links l"
                " JOIN runs r ON r.run_id = l.run_id ORDER BY r.seq, l.position"
            ).fetchall()
        return tuple(
            Link(run_id=run_id, position=position, work_id=work_id, matched_by=matched_by)
            for run_id, position, work_id, matched_by in rows
        )

    def save_links(self, links: Sequence[Link]) -> None:
        """Append links, in one transaction. A record already linked is refused.

        Args:
            links: The new links.

        Raises:
            StoreError: If the database cannot be written, or a record is already linked.
                Nothing is written in that case.
        """
        if not links:
            return
        with self._connection() as connection:
            connection.begin()
            try:
                for link in links:
                    connection.execute(
                        "INSERT INTO links VALUES (?, ?, ?, ?)",
                        [link.run_id, link.position, link.work_id, link.matched_by],
                    )
            except duckdb.ConstraintException as problem:
                connection.rollback()
                raise StoreError(
                    f"{self._database} already links one of these records", [str(problem)]
                ) from None
            connection.commit()
