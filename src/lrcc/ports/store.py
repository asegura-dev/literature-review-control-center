"""The store port: what a feature needs from a review's storage (ADR-0012).

It has one implementation, DuckDB. It exists because a feature may not import an adapter
(ADR-0003) and still needs a type for the store it is handed. It is a typing seam, not an
abstraction over engines: tests use the real implementation in a temporary folder.
"""

from __future__ import annotations

from typing import Protocol

from lrcc.domain.record import Record, SearchResult
from lrcc.domain.runs import LoggedRun, Run


class ReviewStore(Protocol):
    """The storage of one review: its run log, its records and its raw responses."""

    def head(self) -> tuple[int, str]:
        """Return how many runs the log holds, and the hash of its last entry.

        Returns:
            The count and the last hash, or zero and the genesis hash for an empty log.
        """
        ...

    def save_run(self, run: Run, result: SearchResult) -> LoggedRun:
        """Append ``run`` to the log, with its records and its raw responses.

        Args:
            run: The run to append.
            result: The search result the run describes, holding the responses and records.

        Returns:
            The run as logged, with its place in the chain.
        """
        ...

    def log(self) -> tuple[LoggedRun, ...]:
        """Return every logged run, in order."""
        ...

    def read_response(self, run_id: str, file: str) -> bytes | None:
        """Return a stored raw response, or None if its file is not there.

        Args:
            run_id: The run the response belongs to.
            file: The response's file name, as the log records it.

        Returns:
            The file's bytes, or None.
        """
        ...

    def files_on_disk(self) -> dict[str, tuple[str, ...]]:
        """Return what the runs folder really holds: each run folder and the files inside it."""
        ...

    def records(self, run_id: str) -> tuple[Record, ...]:
        """Return the records the database holds for a run, in order.

        Args:
            run_id: The run whose records to read.

        Returns:
            The records, as stored.
        """
        ...
