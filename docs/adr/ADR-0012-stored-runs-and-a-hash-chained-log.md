---
status: accepted (built in v0.5.0; amended by ADR-0016)
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0012 - A search is a stored run: raw responses, records and a hash-chained log

## Context and Problem Statement

`lrcc search` previews what a search string returns and stores nothing (ADR-0011). A review needs
more than a preview. PRISMA counts must be traceable to what each source returned on a given
date, and a replay must rederive every record from stored responses.

ADR-0004 already decided the storage: one DuckDB database per review, raw responses as files
beside it, and no storage port. This record decides what a run is, how it is stored, and how the
log resists quiet edits.

## Decision Drivers

- Every number must be traceable to a stored response.
- Search runs are appended, never edited; a correction is a new entry.
- A truncated retrieval must never look complete.
- A preview must stay possible without writing anything.
- The layering of ADR-0003: a feature never imports an adapter.

## Considered Options

1. **`search` stores a run by default**, and `--preview` keeps the mode that stores nothing.
2. A separate command, `lrcc run`, leaving `search` as the preview.

## Decision Outcome

Chosen option: **option 1**. The stored run is what a review needs, so it is what the plain
command does. The preview is the exception and is asked for by name.

### A run

- **One execution of one search string against one source.** It records:
  - when it started and finished, in UTC;
  - the source, the search string and its SHA-256;
  - the SHA-256 of the protocol the string came from;
  - the count the source reported and the count retrieved;
  - the LRCC version;
  - each raw response's file name, request address, size and SHA-256;
  - the SHA-256 of the records derived from those responses.
- **`run_id`** is its sequence number in the review, the UTC start time and the source, such as
  `0001-20260930T141500Z-pubmed`. It is unique and sorts in order.
- **Retrieval is complete or says it is not.** A run retrieves every record the source reports,
  up to 10,000. When fewer records were retrieved than reported, the run is marked incomplete,
  and the command says so.

### Where it is stored

- **Raw responses** go to `reviews/<review_id>/runs/<run_id>/response-NNNN.raw`, byte for byte as
  received.
- **The database** is `reviews/<review_id>/review.duckdb`, with the run log, the response
  index and the records of every run.
- **SQL is always parameterized.**

### The hash chain

- Each log entry is one canonical JSON document. Its hash is the SHA-256 of the previous entry's
  hash followed by that document.
- Editing, removing or reordering an entry breaks every hash after it.
- `lrcc status` recomputes the chain and reports whether it is intact.
- The chain detects edits to the log. It does not detect a log replaced whole, together with its
  hashes. Anchoring the head outside the file is the bundle's job, in v0.14.0.

### The commands

- **`lrcc search REVIEW_ID --source NAME`** stores a run. With `--preview` it stores nothing, as
  before.
- **`lrcc status REVIEW_ID`** lists the runs with their counts, says whether each used the
  protocol as it stands now, and reports the chain.

### A store port, amending ADR-0004

ADR-0004 said there is no storage port, because DuckDB in memory serves the tests. ADR-0003 says
a feature never imports an adapter. Both cannot hold once a feature saves a run: the feature
needs a type for the store it receives.

**The store gets a port, `ports/store.py`, with one implementation.** It is the typing seam the
layering requires, not an abstraction over engines. There is still one storage engine, no fake
store, and tests use the real DuckDB implementation in a temporary folder.

### Dependency

`duckdb`.

### Consequences

- Good, because a run's counts can be traced to files whose digests anyone can recompute.
- Good, because the log cannot be edited quietly.
- Good, because an incomplete retrieval is visible, not silent.
- Bad, because a port with one implementation departs from "no abstraction without two real
  cases". The rule gave way to the layering rule, and this record says so.
- Bad, because PubMed's `esearch` returns at most 10,000 identifiers. A string that matches more
  produces an incomplete run until paging through NCBI's history server is built.
- Bad, because the chain lives in the same file it protects.

### Confirmation

- CLI tests run a stored search against the mocked transport, and recompute each response file's
  SHA-256 against the log.
- A test edits a log entry directly in the database and asserts that `status` reports the chain
  broken.
- A test asserts that `--preview` writes nothing to the review's folder.
- A test asserts that a run retrieving fewer records than reported is marked incomplete.

## Pros and Cons of the Options

### Option 1 - `search` stores, `--preview` does not

- Good, because the default is the reproducible behaviour.
- Bad, because a person trying a string leaves a run behind unless they ask for a preview.

### Option 2 - A separate `run` command

- Good, because nothing is stored by accident.
- Bad, because there are two commands for one action, and the one named `search` would not be
  the one a review uses.

## More Information

- ADR-0004 (storage), ADR-0011 (the client and the sources).
- Replay and verification of the stored files against the log arrive in v0.7.0.

## Implementation

**v0.5.0** built this record. Details settled while building it:

- **Where things are.** The run and the chain are in `src/lrcc/domain/runs.py`, the port in
  `src/lrcc/ports/store.py`, and the DuckDB store in
  `src/lrcc/adapters/storage/duckdb_store.py`.
- **The log stores each entry as its canonical JSON**, next to the two hashes. The chain is
  verified over exactly the text that is stored. The response index is part of the entry, so
  there is no separate table for it.
- **Files are written before the log entry** that names them. A failure in between leaves a run
  folder that no entry names, never an entry that names a missing file.
- **A failed search stores nothing**: no folder, no entry, no database.
- **`status` writes nothing.** A review without runs has no database, and asking for its status
  does not create one.
- **`status` exits with code 1 when the chain does not verify**, so a script can act on it.
- **`status` prints one line per run, not a table.** In a narrow terminal a table split the run
  identifier over two lines, which a test caught. An identifier has to stay whole to be copied.
- **arXiv is paged**, 100 entries per request, until it has delivered what it reported or an
  empty page ends it. PubMed asks `esearch` for at most 10,000 identifiers.
- **`--limit` with a run** stores a run that is marked incomplete when the limit is below the
  reported count. That is deliberate: the run says what it did.
- **No real request was made while building this phase.** The real commands were run only for
  `status` on a review without runs, and for a run refused because the network was off.
