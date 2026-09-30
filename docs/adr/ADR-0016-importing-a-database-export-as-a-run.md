---
status: proposed
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0016 - A database's RIS export is imported as a run

## Context and Problem Statement

Some searches cannot go through an API, at least not yet:

- IEEE Xplore approves each key by hand, and until then refuses every request.
- Scopus grants the COMPLETE view, the one that carries abstracts, only from the institution's
  network or VPN. From elsewhere its API answers in the STANDARD view, without abstracts. The
  maintainer works from home.

The databases' own web interfaces, reached through a library's remote access, still run the same
string and export the records with their abstracts. The roadmap planned for this case in v0.8.0:
Scopus and IEEE Xplore "by API if a key exists, by importing manual exports otherwise".

An export must not become the weak link of identification. Its counts must trace to a stored
file, as an API run's do (ADR-0012), and its records must be rederivable offline (ADR-0013).

## Decision Drivers

- Every number must be traceable to a stored file, and `verify` and `replay` must cover it.
- PRISMA-S reports each search's database, exact string and date. An import happens after the
  search, so the date of the search is not the date of the import.
- A truncated export, or one imported twice, must not pass silently.
- No new dependency for a format that takes a few lines to read.
- The file comes from outside: it is data, never instructions.

## Considered Options

1. **RIS files, stored as a run in the same log.**
2. RIS and CSV files, stored as a run in the same log.
3. RIS files, kept in a separate import log.

## Decision Outcome

Chosen option: **option 1**. Both databases export RIS with abstracts, and so do most others,
so one reader serves every case. A run in the same log gets `status`, `verify` and `replay` for
free.

### The command

`lrcc import REVIEW_ID FILE... --source NAME --searched YYYY-MM-DD --reported N`

- **`--source`** must be a source the protocol names. The run records the protocol's string for
  that source, and that is the string the person runs in the database's interface.
- **`--searched`** is the day the search was run in the database. It is required, because it is
  the date PRISMA-S reports. A day after tomorrow, in UTC, is refused as a typing error; the
  day of tolerance covers every time zone.
- **`--reported`** is the count the database showed for the search. It is required. When the
  files hold fewer records, the run is stored and marked incomplete, as an API run that
  retrieved less than reported is.
- **Several files** make one run, for a search exported in parts: databases cap how many records
  one export holds. The records keep the order of the files as given.

### What is stored

- Each file is stored byte for byte as `response-NNNN.raw`, with its size and SHA-256. The
  address recorded for it is the file's name.
- The run gains one field, `imported`, holding the format and the day of the search.
- **This amends ADR-0012.** A field added to a run after v0.7.0 is optional, and is left out of
  the canonical entry while empty. Every entry written before it keeps its canonical form, and so
  its hash.
- **A file already stored in the review is refused**, and so is a file given twice in one
  command. Either would count its records twice.

### Reading RIS

- A record runs from a `TY` line to an `ER` line, with one `TAG  - value` per line. A line
  without a tag continues the value before it.
- The fields read, taking the first tag that holds a value:

  | Field | Tags |
  |---|---|
  | title | `TI`, then `T1` |
  | authors | `AU`, then `A1` |
  | year | the first four digits of `PY`, `Y1` or `DA` |
  | DOI | `DO`, in lowercase |
  | abstract | `AB`, then `N2` |

- **A record's identifier within its source**, in this order:
  1. Scopus's EID, when the record's link carries one. It is the identifier Scopus's API gives
     the same record.
  2. The DOI.
  3. `ris-` followed by the first 16 hex digits of the SHA-256 of the record's fields.
- **Refused, never half read:** a file that is not UTF-8 (a byte-order mark is accepted), text
  outside a record, a record inside another, a file that ends inside a record, and a file with
  no record.
- LRCC has its own reader, with no new dependency.

### Verify and replay

`verify` needs no change. `replay` rereads an imported run's files with the RIS reader. It needs
no adapter, no key and no network.

### Not in this record

- **Records found by other methods**, such as citation searching. PRISMA 2020 counts them apart
  from database searches, so importing them needs a way to say which they are. Later in v0.8.0.
- **CSV and BibTeX**, and databases without an adapter, such as Web of Science: a protocol names
  only the four known sources.
- **`check-query` against an imported run.**

### Consequences

- Good, because a search with abstracts can be made through a database's web interface, from
  wherever the library's remote access reaches.
- Good, because an imported run is logged, verified and replayed like any other.
- Good, because a truncated export shows as incomplete, and a double import is refused.
- Bad, because LRCC does not run the search itself. The log records what the person says they
  ran: the string, the day and the count. LRCC cannot confirm that the string run was the
  protocol's.
- Bad, because the reader rests on Scopus and IEEE Xplore writing standard RIS. It is tested
  against synthetic files until a real export is imported.
- Bad, because the identifier's kind depends on what the export carries: an EID, a DOI or a
  digest.

### Confirmation

- Tests read synthetic Scopus and IEEE Xplore exports, including a value continued on a second
  line and a record with neither EID nor DOI.
- Command tests import a file and assert:
  - the stored file and its digest;
  - the records and their identifiers;
  - the day of the search;
  - that `status`, `verify` and `replay` accept the run, with the network off.
- Tests refuse each broken file named above, a double import, a future day, and a source the
  protocol does not name. After each refusal, nothing is stored.
- A test asserts that an entry written before the new field keeps its canonical form.

## Pros and Cons of the Options

### Option 1 - RIS, as a run in the same log

- Good, because one reader serves Scopus, IEEE Xplore and most other databases.
- Good, because `status`, `verify` and `replay` need almost no change.
- Bad, because some databases write RIS loosely. Such files are refused, not guessed at.

### Option 2 - RIS and CSV

- Good, because a CSV export is easy to inspect in a spreadsheet.
- Bad, because each database writes its own columns, so there would be one reader per database
  instead of one reader for all.

### Option 3 - A separate import log

- Good, because imports and API runs could never be confused.
- Bad, because `status`, `verify`, `replay` and later PRISMA would each read two logs, and the
  order of events between them would be lost.

## More Information

- ADR-0012 (what a run records), which this record amends; ADR-0013 (verify and replay);
  ADR-0015 (the Scopus and IEEE Xplore adapters).
- PRISMA-S: Rethlefsen et al., 2021, Systematic Reviews 10:39.

## Implementation

**v0.8.0** built this record, while it was still proposed. Details settled while building it:

- **Where things are.**
  - The reader: `src/lrcc/domain/ris.py`. It sits in the domain, because both the import and
    `replay` use it, and a feature never imports another.
  - The command's use case: `src/lrcc/features/imports.py`.
  - The run's `imported` field: `src/lrcc/domain/runs.py`.
- **Every run has a search day.** `Run.searched_on` is the day given for an import, and the UTC
  day it started for an API search. `status` prints it for imports, and `status --json` gives
  it for every run, with `imported` saying which kind the run is.
- **The recorded address of an imported file is its name**, without its folder.
- **A file over 50 MB is refused**, the ceiling the HTTP client puts on one answer.
- **Checked against bytes the previous code wrote.** A run was stored with the code of the last
  commit, which writes v0.7.0's format, and then read with the new code:
  - `status`, `verify` and `replay` accepted it;
  - an import was appended to the same log, and all three accepted both runs;
  - importing the same file again was refused.
- **Each new check was broken on purpose, and a test failed each time**:
  - the canonical form;
  - the refusal of a double import;
  - the refusal of a future day, and its day of tolerance;
  - the refusal of a file cut short;
  - the EID rule;
  - the replay of an import.
- **No real export has been imported yet.** The reader is tested against synthetic files only.
