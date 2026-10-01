# Changelog

All notable changes to LRCC are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0, a minor version may
break anything; every break is named here.

## [0.10.0] - Unreleased

A person screens each work by its title and abstract, starting with a pilot, and every decision
is kept in a hash-chained log with the protocol it was made under.

### Added

- **`lrcc screen REVIEW_ID [--pilot]`**, a terminal session over the works still to screen
  (ADR-0019).
  - Each work shows its title, authors, year, sources, DOI and longest abstract.
  - One key decides: include, exclude (then an exclusion code of the protocol), uncertain. Other
    keys add a note, skip or stop.
  - Each decision is written as it is made.
  - The order is the SHA-256 of the review id and the `work_id`: random-looking, reproducible,
    stored nowhere.
  - `--pilot` presents the first 50 works of that order and the frontier cases from
    `frontier.yaml`, and marks its decisions as the pilot's.
- **`lrcc screen REVIEW_ID --work WORK_ID --decision include|exclude|uncertain [--code]
  [--note]`** records one decision without the session.
- **`lrcc screen-report REVIEW_ID`.** It reports the pilot and the whole screening: included,
  excluded by code, uncertain and pending. It also gives the decisions per protocol digest, the
  reviewer, and any frontier case the searches did not find.
- **The protocols decisions were made under are kept**, in `protocols/<sha256>.yaml` beside the
  review's database, so an amendment after the pilot can always be read.

### Changed

- **The counted runs.** For each source, the review counts its latest run whose search string is
  the protocol's current one. An amendment of the criteria no longer uncounts the searches.
  `dedupe` reports over the counted runs, under the JSON key `counted_runs`, where it used
  `current_protocol`.
- **`verify` checks the screening log's chain**, and that every kept protocol matches its name.
- **One chain check serves all three hash-chained logs**, and the picture of a review's works is
  assembled once, for deduplication and screening alike.

## [0.9.0] - Unreleased

Records become works. Exact duplicates are joined through the identifiers they share, and a
person confirms the rest, which are proposed by title.

### Added

- **`lrcc dedupe REVIEW_ID`.** It joins every record not yet linked to its work, in log order
  (ADR-0017).
  - Records join through a shared DOI, PMID, arXiv identifier, or a database's own identifier
    for the record. A record with none of the first three is joined only to records that also
    have none, on its normalized title and year.
  - Each join keeps the identifier that made it. The report gives, per run, the records that
    first named a work and those already seen. For the runs under the current protocol, it
    gives the records, the works and the duplicates removed.
  - A record that carries identifiers of two different works stops the pass, and nothing is
    written. So does a new work whose name is already taken.
  - It refuses a review whose run log does not verify or whose records were edited.
- **`work_id` and the work catalog** (ADR-0006): `library/catalog.duckdb`, shared by the
  workspace's reviews. A work is named once, as `<author><year>-<hash6>`, and every identifier
  met later becomes an alias.
- **`lrcc candidates REVIEW_ID [--min 0.80] [--csv FILE]`.** It lists the pairs of works whose
  titles score 0.80 or more and that no identifier joined, for a person to judge (ADR-0018).
  The default comes from the first review's real records. With `--csv` it writes the pairs to a
  new file, never over an existing one, escaping cells that begin like a formula.
- **`lrcc decide REVIEW_ID FILE`.** It reads that file back once a person has filled the
  `decision` column with `same` or `different`, and appends each decision to a hash-chained log.
  The log records the reviewer, the time, the score and the note.
  - Works joined by `same` form a group, named by the published version over the preprint.
  - A later decision on a pair is a new entry that replaces the earlier one.
  - Empty rows wait for later.
  - An unknown decision or work, a pair given twice with two decisions, or a contradiction
    refuses the whole file.
- **`reviewer` in the configuration**, the person decisions are attributed to. `decide` refuses
  to run without it.

### Changed

- **A review's database gains a `links` table**, one row per record with its work and the reason
  it joined, and a `decisions` table, the person's log. Both are created, empty, the next time
  any command opens the database.
- **`dedupe` counts groups.** For the current protocol's runs it reports the works after
  deduplication, and the duplicates removed by identifiers and by a person.
- **`verify` checks the decisions' chain** as it checks the runs'.

## [0.8.0] - Unreleased

Scopus and IEEE Xplore join PubMed and arXiv, through API keys that LRCC uses and never keeps,
or through the RIS files their web interfaces export.

### Added

- **`lrcc import REVIEW_ID FILE... --source NAME --searched YYYY-MM-DD --reported N`.** It stores
  the RIS files a database exported for the protocol's string as a run (ADR-0016). Use it when a
  search cannot go through the API: a key awaiting approval, or abstracts granted only through
  the database's own interface.
  - Each file is kept byte for byte, in the same hash-chained log, so `status`, `verify` and
    `replay` treat the run like any other.
  - The run records the day of the search and the count the database reported. It is marked
    incomplete when the files hold fewer records.
  - A file already stored in the review is refused, and so is a file that is not RIS or ends
    inside a record.
- **Two sources, Scopus and IEEE Xplore.** `search` (stored or `--preview`), `check-query` and
  `replay` work with all four sources (ADR-0015).
  - IEEE Xplore uses the Metadata Search API, 200 records per call. It does not retry a refusal,
    because the free key allows 200 calls a day. Its gold check searches the DOI as a field of
    the query, `("DOI":...)`, joined to the string by `AND`. The API's `doi` parameter ignores
    the string, as a real control showed.
  - Scopus uses the Scopus Search API in the COMPLETE view, for abstracts, with cursor paging.
    The key and the institutional token go in headers.
- **API keys from a `.env` beside the configuration file**, and from nowhere else. The real
  environment wins over the file. Only `SCOPUS_API_KEY`, `SCOPUS_INSTTOKEN`, `IEEE_API_KEY` and
  `NCBI_API_KEY` are read. A missing key is reported by its name and the file that should hold it.
  `NCBI_API_KEY`, if set, raises PubMed's rate limit.
- **Keys are never kept.** In detail:
  - a key sent as a query parameter is recorded as `[redacted]`;
  - a key sent as a header is not recorded at all;
  - an answer that repeats a key is refused;
  - error quotes are scrubbed;
  - the object holding the keys prints only their names.
- **`config.example.yaml` and `.env.example`**, versioned without any personal value.

### Fixed

- **The reported count of a paged search** is now the count from the first page. A later page,
  and above all the last, can report something else, and one test saw Scopus's last page report
  zero.

### Changed

- **A person's configuration sits beside their `.env`.** Git ignores `config*` at the root of the
  repository, except the example.
- **A run may record that it was imported** (ADR-0016, amending ADR-0012). The field is left out
  of a search's log entry, so every entry written by earlier versions still verifies.
- **`status --json` gives each run's `searched_on` day**, and says whether the run was `imported`.

## [0.7.0] - Unreleased

What a review stores can be checked against its log, and every run can be reproduced from its
stored responses without the network.

### Added

- **`lrcc check-query REVIEW_ID --source NAME`.** It checks the protocol's string against the
  review's gold set, `reviews/<review_id>/gold.yaml`. Each work is retrieved, missed, not indexed
  by the source, or unknown for lack of an identifier; only a miss counts against the string.
  It exits with code 1 on any miss (ADR-0014).
- **`lrcc verify REVIEW_ID`.** It recomputes the hash chain, the SHA-256 and size of every stored
  response, and the digest of the records in the database, and compares each with the log. It
  also names files and run folders the log does not know about. It exits with code 1 on any
  mismatch (ADR-0013).
- **`lrcc replay REVIEW_ID`.** It rederives every run's records from its stored responses, with
  no request, and says whether they are the records the run logged. It changes nothing, and
  exits with code 1 if any run is not reproduced.

### Fixed

- **PubMed book records were dropped.** `efetch` answers with `PubmedBookArticle` for books and
  book chapters, and only `PubmedArticle` was read. The first real run reported 2,499 records
  and retrieved 2,489; the ten missing were book records. Both kinds are now read, in order.
  A run stored before this fix replays as different, which is accurate: re-run it.

### Changed

- **The source port gains `records_from`.** A search and a replay derive records with the same
  code, from the raw answers alone.

## [0.5.0] - Unreleased

A search becomes a stored run: what each source returned is kept, and the log of runs cannot be
edited quietly.

### Added

- **Stored runs.** `lrcc search REVIEW_ID --source NAME` now stores the run (ADR-0012):
  - every raw response, byte for byte, under `reviews/<review_id>/runs/<run_id>/`;
  - the records, in `reviews/<review_id>/review.duckdb`;
  - a log entry with the UTC times, the search string and its SHA-256, the protocol's SHA-256,
    the reported and retrieved counts, the LRCC version, and each response's size and SHA-256.
- **A hash-chained run log.** Each entry's hash covers the entry and the hash before it, so an
  edit, a removal or a reordering is detected.
- **`lrcc status REVIEW_ID`.** It lists the runs with their counts, says whether each used the
  protocol as it stands now, and verifies the chain. It exits with code 1 if the log was edited.
- **Complete retrieval, or a statement that it is not.** A run retrieves every record the source
  reports, up to 10,000, paging arXiv as needed. A run that retrieved fewer records than
  reported is marked incomplete, and the command says so.
- **Runtime dependency:** duckdb (ADR-0004).

### Changed

- **`lrcc search` stores by default.** The mode that stores nothing is now `--preview`.
- **ADR-0004 amended by ADR-0012:** the store has a port, with one implementation, because a
  feature may not import an adapter.

## [0.3.0] - Unreleased

The first search: a protocol's string run against PubMed or arXiv, through a client that contacts
only the hosts the configuration names.

### Added

- **`lrcc search REVIEW_ID --source pubmed|arxiv`.** It runs the protocol's search string for
  that source and prints the count the source reported, the count retrieved and the records. It
  takes `--limit`, `--config` and `--json`. It is a preview: nothing is stored yet (ADR-0011).
- **Network settings in the configuration.**
  - The network is off unless `network.enabled` is `true`.
  - `network.hosts` is the allowlist. Each host carries `min_interval`, the seconds to leave
    between two requests to it.
- **One HTTP client.** It refuses, before anything is sent:
  - any request while the network is off;
  - a host that is not listed;
  - anything but HTTPS on the default port.

  It never follows a redirect. It retries transport errors, HTTP 429 and HTTP 5xx with backoff,
  four attempts in all, and refuses a response above 50 MB.
- **The source port**, with PubMed (E-utilities) and arXiv (Atom API) as its two
  implementations. XML is parsed with `defusedxml`; a document that declares entities is
  refused.
- **A frozen `Record`:** source, the source's identifier, title, authors, year, DOI and abstract.
- **Two gate checks:**
  - no module but the HTTP client may import a networking library;
  - every test fails if it opens a real connection.
- **Runtime dependencies:** httpx, tenacity, defusedxml (ADR-0011).

### Changed

- **Roadmap:**
  - v0.4.0 is merged into v0.3.0;
  - `work_id` and its catalog move to v0.9.0, with deduplication;
  - secrets move to v0.8.0, with the first source that requires a key.

## [0.1.0] - Unreleased

The first commands: create a review and check its protocol, inside a workspace that refuses to
expose what it holds.

### Added

- **`lrcc init REVIEW_ID`.** Creates `library/` and `reviews/<review_id>/protocol.yaml` in the
  workspace, from a synthetic template, and prints the protocol's SHA-256. It never overwrites
  an existing review. The template is pinned to LF line endings, so `init` writes the same bytes,
  and prints the same digest, on every platform (ADR-0010).
- **`lrcc validate REVIEW_ID`.**
  - It checks every field of the protocol and reports every problem in one pass, each located
    by field.
  - When the protocol is valid, it prints its criteria, sources, extraction fields and the
    SHA-256 of the file's exact bytes: the digest to register.
- **`--json` on both commands**, for results and errors alike (ADR-0005).
- **Configuration.**
  - It is a YAML file with one required field, `workspace`, which must be a non-empty absolute
    path.
  - It is named by `--config` or `LRCC_CONFIG`. There is no default location.
  - Unknown fields are errors.
- **Protocol format 1.**
  - Its sections are the question with its framework, coded INC/EXC criteria, one search
    string per known source (`pubmed`, `arxiv`, `scopus`, `ieee`) and extraction fields.
  - Every field is required.
  - It is parsed with `yaml.safe_load`, so a protocol cannot run code.
- **The workspace boundary (ADR-0006).** LRCC refuses a workspace that:
  - does not exist;
  - is inside a git working tree;
  - is under a folder named by the `OneDrive`, `OneDriveCommercial` or `OneDriveConsumer`
    variables.

  Every path is resolved before it is checked, so `..`, symlinks and junctions cannot lead
  outside.
- **Runtime dependencies:** pydantic, pyyaml, typer, rich (ADR-0010).

### Changed

- **Coverage threshold.** The gate now fails below 95% coverage, as ADR-0002 deferred to the
  first real code.
- **ADR-0003 amended by ADR-0010:**
  - the domain may parse YAML;
  - views may import domain types and errors.

  The check that views decide nothing is unchanged.
- **Roadmap:**
  - v0.2.0 is merged into v0.1.0;
  - network settings and allowed hosts move to v0.3.0;
  - secrets move to v0.4.0.

## [0.0.1] - 2026-09-29

The scaffold: an empty package, the gate that will judge everything added to it, and the decisions
that shape it.

### Added

- **Package.** An installable package, `literature-review-control-center`, importing as `lrcc`.
  It uses a `src` layout, the `uv_build` backend, Python 3.12, and a committed lockfile. It has
  no runtime dependencies (ADR-0002, ADR-0007).
- **Layers.** The empty layers `domain`, `ports`, `adapters`, `features` and `views`, each
  documented with what it may import (ADR-0003).
- **Quality gate**, configured in `pyproject.toml`: `ruff check`, `ruff format --check`, `mypy`
  in strict mode, and `pytest` with branch coverage reported but no threshold yet (ADR-0002).
- **`tests/test_layering.py`**, which checks the layout in both directions:
  - inward, every import respects its layer, and nothing imports LACC;
  - outward, no function in a view does work that touches no presentation.

  Each rule is proven able to fail on every run (ADR-0003, ADR-0001).
- **`tests/test_no_listening_port.py`.** The package contains no server-side networking
  (ADR-0005).
- **Commit-message check.** `scripts/check_commit_message.py` rejects co-author trailers,
  "generated with" lines and session trailers. It runs as a `commit-msg` hook and in CI over
  every new commit (ADR-0008).
- **pre-commit** with ruff, mypy, gitleaks and the commit-message hook.
- **`run.ps1` and `scripts/uv_run.py`**, which keep the virtual environment outside the checkout
  and outside synchronised folders. A test fails if the two disagree (ADR-0002).
- **CI.** GitHub Actions runs the gate on Ubuntu and Windows.
- **Documentation:**
  - `PRINCIPLES.md`, `VISION.md` and this changelog;
  - chapters 0 (brief), 1 (architecture) and 2 (roadmap);
  - the development guide;
  - decision records ADR-0001 to ADR-0009, with an index;
  - the phase notes of v0.0.1.
- **License.** The MIT license (ADR-0009).

[0.0.1]: https://github.com/asegura-dev/literature-review-control-center/releases/tag/v0.0.1
