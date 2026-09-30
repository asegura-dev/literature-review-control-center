---
status: accepted (built in v0.5.0; amended by ADR-0012)
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0004 - One DuckDB database per review, raw responses beside it, and no storage port

## Context and Problem Statement

A review accumulates:

- search runs with their raw responses;
- thousands of records;
- merge decisions from deduplication;
- hash-chained screening and eligibility decisions;
- the full-text map with digests;
- PRISMA counts, which are queries over the states of works.

It exports CSV, Parquet and JSON. A replay must rederive everything from stored responses and
produce identical outputs.

Something has to hold this state durably. The choices are what that something is, how many
there are, and whether the program talks to it through an abstraction.

## Decision Drivers

- PRISMA counts are queries, so the store must answer aggregate queries cleanly.
- Exports to Parquet and CSV must be simple and correct.
- Raw responses must be stored exactly as received, with a digest, so a replay can prove it read
  the same bytes.
- Tests must run fast, offline, without a server.
- No abstraction without two real cases: a storage port needs two real storage engines.
- A review must be archivable, backed up and deletable as a unit.

## Considered Options

1. **One DuckDB file per review**, raw responses as files beside it, no storage port.
2. One SQLite file per review.
3. One DuckDB file for the whole workspace, shared by all reviews.
4. No database: JSON Lines logs plus Parquet files, queried by hand.

## Decision Outcome

Chosen option: **option 1**.

- **Location.** Each review's database is `reviews/<review_id>/review.duckdb` inside the
  workspace (ADR-0006).
- **Raw responses** are stored as files under `reviews/<review_id>/runs/<run_id>/`, byte for byte
  as received. The database records each file's path, relative to the review, and its SHA-256.
- **Replay** reads those files, never the database's derived tables. It can therefore rebuild the
  derived tables and compare them.
- **No storage port.** The program uses DuckDB directly through one adapter under
  `adapters/storage/`. Tests use DuckDB in memory, which is the same engine and not a mock.
- **SQL is always parameterized.**
- Exports use DuckDB's own writers for Parquet and CSV. CSV cells that begin with `=`, `+`, `-`
  or `@` are sanitized first.
- **Refused:** an ORM, a migration framework, and any database server. Schema changes are
  versioned by a number stored in the database, and handled when the first one is needed.

### Consequences

- Good, because PRISMA counts, deduplication candidates and exports are SQL over one file, and
  DuckDB writes Parquet natively.
- Good, because a review is a folder: copy it to archive it, delete it to remove it.
- Good, because raw responses are ordinary files whose digests anyone can recompute, independently
  of DuckDB.
- Good, because tests use the real engine in memory, and there is no fake to drift from it.
- Bad, because DuckDB allows one writing process at a time. A long `search` and a `status` in a
  second terminal can collide. For a single-user CLI this is acceptable, but it must fail with a
  clear message, not a traceback.
- Bad, because one review's database knows nothing of another's. The library of full texts is
  shared across reviews, so recognising that a work in one review is the same work already in the
  library needs a workspace-level work catalog, `library/catalog.duckdb`. It holds identity
  only, and it is specified in ADR-0006.
- Bad, because depending directly on DuckDB means that replacing it would touch every query in
  the storage adapter. That is the accepted price of not abstracting over one case.
- Bad, because a database file inside a synchronised folder (OneDrive, Dropbox) can be locked or
  copied mid-write. ADR-0006 handles where the workspace may live.

### Confirmation

- There is no module under `src/lrcc/ports/` about storage.
- Tests open DuckDB with `:memory:` or in a temporary directory, never in a real workspace.
- A replay test rebuilds the derived tables from stored response files and compares them with
  the originals.

## Pros and Cons of the Options

### Option 1 - DuckDB per review

- Good, because it is analytic SQL with native Parquet, in one file per review.
- Bad, because it has a single writer, and it is a dependency with its own storage-format
  evolution.

### Option 2 - SQLite per review

- Good, because it is in the standard library (no dependency), mature, and its file format is
  stable for decades.
- Good, because it tolerates several readers alongside one writer well.
- Bad, because Parquet export needs another dependency (for example `pyarrow`).
- Bad, because the analytic queries behind PRISMA and deduplication are clumsier to write.
- Neutral: a real alternative, not a straw man. If DuckDB's single-writer limit or format changes
  prove painful, this is the fallback, and it would still not need a port until both exist in
  the code.

### Option 3 - One DuckDB for the workspace

- Good, because cross-review questions (is this work already in the library?) are one query.
- Bad, because every review shares one file: one corruption, lock or format upgrade affects all
  of them, and a review cannot be archived or deleted on its own.

### Option 4 - Files only

- Good, because it needs no database dependency, and everything is plain text or Parquet.
- Bad, because every count, join and deduplication query is written by hand. That is where
  counting errors hide, and PRISMA counts must come from a query.

## More Information

- **A premise to verify before v0.5.0**, not assumed here: DuckDB's guarantees for reading a
  database file written by an earlier version. A review must stay readable for years after its
  paper. The export to Parquet and the stored raw responses are the long-term record; the
  `.duckdb` file is a working store that can be rebuilt by replay.

## Amendments

- **ADR-0012 (2026-09-30, v0.5.0). There is a store port, with one implementation.** This record
  said there would be none. A feature may not import an adapter (ADR-0003), and a feature that
  saves a run needs a type for the store it is handed. The port is that typing seam. There is
  still one storage engine and no fake store: tests use the real DuckDB implementation in a
  temporary folder.
- **The raw responses of a run** are stored under `reviews/<review_id>/runs/<run_id>/`, as this
  record decided, named `response-NNNN.raw`.
