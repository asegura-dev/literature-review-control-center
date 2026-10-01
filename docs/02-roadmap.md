# Chapter 2 - Roadmap: where LRCC is and where it is heading

This chapter describes the route to v1.0 and the direction after it. Nearer phases are described with more confidence; later ones are direction, and are expected to change as real code reveals what each one needs. It is not a schedule and carries no dates.

## Status

This roadmap was written on 2026-09-28, before the first commit.

- **v0.0.1, Scaffold,** was built on 2026-09-29 and merged into `main` through pull request #1. Its gate is green in CI on Linux and Windows ([phase notes](phases/v0.0.1.md)).
- **v0.1.0, Configuration, protocol and workspace,** was built on 2026-09-29, and its gate is green locally ([phase notes](phases/v0.1.0.md)). It delivers LRCC's first two commands, `lrcc init` and `lrcc validate`.
- **v0.3.0, One HTTP client and the first two sources,** was built on 2026-09-30, and its gate is green locally ([phase notes](phases/v0.3.0.md)). It delivers `lrcc search` for PubMed and arXiv.
- **v0.8.0, Scopus and IEEE Xplore, is the current phase.** Its first part was built on 2026-09-30 ([phase notes](phases/v0.8.0.md)): API keys read from a `.env` beside the configuration and never recorded, and the Scopus and IEEE Xplore adapters. The maintainer accepted its decision records, ADR-0015 and ADR-0016, the same day. The maintainer's first requests with real keys, the same day, were refused: IEEE Xplore answered `Developer Inactive`, because the key still awaits IEEE's approval, and Scopus answered `APIKEY_INVALID`. Later that day Scopus accepted the key. The gold check ran in the STANDARD view and retrieved every gold work Scopus can be asked about, but the COMPLETE view, which carries abstracts, was refused from outside the institution's network. IEEE Xplore's key was approved the same day. Its string reported 500 records. A control showed that its gold check could never report a miss, because the API's `doi` parameter ignores the string. Once fixed, the check retrieved every gold work IEEE Xplore holds. Its second part, built the same day, is `lrcc import`: a database's RIS export stored as a run, for searches made through the database's web interface (ADR-0016). No real export has been imported yet. Records found by other methods, and notifying long runs, remain.
- **v0.6.0, check-query.** It was built on 2026-09-30, after v0.7.0, and is released with it in 0.7.0 ([phase notes](phases/v0.6.0.md)). The maintainer accepted its decision record, ADR-0014, the same day, and ran the first real check: on PubMed the string retrieved every gold work that PubMed holds, with no miss, though most of those works came from an earlier PubMed run of the string. CI passed on Linux and Windows for everything up to this phase.
- **v0.7.0, Verify and replay,** It was built on 2026-09-30, and its gate is green locally ([phase notes](phases/v0.7.0.md)). The maintainer accepted its decision record, ADR-0013, and ran its real scenario the same day: the two arXiv runs replayed as identical, and the PubMed run replayed with the ten book records the first adapter had dropped.
- **v0.5.0, Stored runs,** was built on 2026-09-30, and its gate is green locally ([phase notes](phases/v0.5.0.md)). `lrcc search` now stores a run, and `lrcc status` lists the runs and checks the log. The maintainer made the first real run the same day: arXiv reported 106 records for the example string, and run `0001-20260930T145901Z-arxiv` was stored with its counts and date. The phase waits for CI and the maintainer's acceptance.

On 2026-09-29, ADR-0010 merged the v0.2.0 row into v0.1.0, because `init` needs the workspace boundary. The same record moved network settings and allowed hosts to v0.3.0, and secrets to v0.4.0, where the code that reads them arrives. Later version numbers did not change.

On 2026-09-30, ADR-0011 merged the v0.4.0 row into v0.3.0, because an HTTP client with no source delivers nothing to run. The same record moved `work_id` and its catalog to v0.9.0, where deduplication first creates works, and secrets to v0.8.0, where Scopus is the first source that requires a key.

On 2026-09-29 the nine founding decision records (ADR-0001 to ADR-0009) were drafted, and the maintainer accepted them the same day. Drafting them amended this chapter in five places:

- The API-reference generator moved from v0.0.1 to v0.14.0.
- `init` was placed in v0.1.0; it had no version.
- The workspace-level work catalog was placed in v0.3.0.
- The AI coding assistant's operating instructions left the v0.0.1 deliverables, because they live outside the repository (ADR-0008).
- Premises on third-party replay and on DuckDB file compatibility were added.

## How a version is done

Every version closes the same way. A decision record precedes the code. The code is covered by tests that exercise the path the program actually runs. The quality gate is green. The documentation is true: the ADR, the CHANGELOG, the chapter the change belongs to, the guides and this roadmap. A version whose documents do not match what the program does is not finished, however green its gate.

## The route to v1.0

| Version | Capability | Done when |
|---|---|---|
| v0.0.1 | Scaffold: uv package (`src` layout); quality gate (ruff, strict mypy, pytest) in CI on Linux and Windows; pre-commit with gitleaks and a commit-msg hook that rejects AI attribution trailers; documentation system (chapters, guides including the development guide, ADRs); the nine founding ADRs decided; PRINCIPLES, VISION, LICENSE; `run.ps1` keeping the environment outside synchronised folders; layering tests in both directions, each seen to fail on purpose | the gate is green on an empty package |
| v0.1.0 | Configuration, protocol and workspace (ADR-0010): a frozen `Config` loaded from YAML, named by `--config` or `LRCC_CONFIG`; the review protocol in YAML (search strings per source, INC/EXC codes, extraction schema) hashed over its exact bytes; a workspace with a boundary, outside any git working tree and any detectable synchronised folder, holding `library/` and `reviews/<id>/`; `lrcc init` and `lrcc validate`, with `--json` | an empty required value is a clear error, never a silent default; a workspace inside a repository is refused, and so is a path that escapes the boundary |
| v0.2.0 | Merged into v0.1.0 (ADR-0010) | |
| v0.3.0 | One HTTP client and the first two sources (ADR-0011): a host allowlist with a rate limit per host, retries, and the network off by default, all in the configuration; defusedxml; a frozen `Record`; the source port with its two real cases, PubMed and arXiv, tested against synthetic fixtures; `lrcc search`, a preview that stores nothing | the gate fails if anything but the one client can reach the network, and the client refuses an unlisted host before sending; `search` runs offline against fixtures |
| v0.4.0 | Merged into v0.3.0 (ADR-0011) | |
| v0.5.0 | Stored runs (ADR-0012): `lrcc search` stores each raw response with its digest, the records, and a hash-chained run log in a DuckDB database per review; `--preview` stores nothing; `lrcc status` lists the runs and verifies the chain; the first real run of the first review | real counts are recorded with their date and query version |
| v0.6.0 | `check-query` (ADR-0014): a search string against a gold set, per source, telling a miss by the string from a work the source does not hold; built after v0.7.0 and released with it | the string retrieves the whole gold set, or every gap is recorded with its reason |
| v0.7.0 | `verify` checks every stored response and record against the log; `replay` rederives every run's records from its stored responses, offline (ADR-0013); PubMed book records are read | a replay produces identical outputs; a re-run is documented as a different run |
| v0.8.0 | Scopus and IEEE Xplore (by API if a key exists, by importing manual exports otherwise; the API adapters and the keys were built first, ADR-0015, then the import of RIS exports, ADR-0016); secrets only from `.env`, for the first key a source requires; the same import serves records found by other methods; ntfy for long runs | four sources unified; a long run says when it is done |
| v0.9.0 | Exact and fuzzy deduplication, incremental, with a threshold measured on real data and a merge log; a deterministic `work_id`, assigned once, with later identifiers kept as aliases in a workspace-level catalog (ADR-0006) | a new batch is deduplicated against what exists; fuzzy merges are confirmed by a person |
| v0.10.0 | Title/abstract screening in the CLI: append-only, hash-chained decisions; an "uncertain" state; a pilot; versioned protocol amendments | correcting a decision adds an entry, never edits one |
| v0.11.0 | Full-text retrieval: the list of texts to obtain, with known links (arXiv, PMC); a read-only `scan` (real PDF, size ceiling, SHA-256, provenance); "not retrieved" with a reason | nothing is moved or renamed: the command is suggested and a person runs it |
| v0.12.0 | Full-text eligibility with coded reasons, bound to the digest of the PDF that was read | every exclusion has a reason and the exact document version |
| v0.13.0 | PRISMA 2020 report derived from states (both identification columns, the retrieval boxes), flow diagram, public supplement without licensed content, PRISMA-S documentation of the search | the diagram comes from a query |
| v0.14.0 | Review bundle v1 as the contract: manifest, digests, versioned JSON Schema; `export`; `--json` on every command; a documented public Python API with a generated reference (its generator decided by its own record) | a test consumer validates a bundle without importing the package |
| v0.15.0 | Adoption: usage, operations and development guides; a clean install verified on a fresh machine; CITATION.cff and a Zenodo DOI; an honest README status | someone follows the guides without asking |
| **v1.0.0** | A real review executed end to end against the real databases | a third party reproduces its counts by replay from a clean install, and the bundle entered LACC |

## Premises not yet measured

A plan is where unmeasured claims hide, so these are written down as premises, each with the point before which it must be checked:

- whether the institution's subscription includes access to the Scopus API (before v0.8.0);
- whether IEEE grants an API key for this use, or IEEE Xplore stays an import (before v0.8.0);
- what each provider's terms allow for storing and redistributing content (before v0.13.0, because of the public supplement);
- the fuzzy deduplication threshold, which is measured on real data in v0.9.0 and never borrowed from a convention;
- where LACC points its workspace relative to the library (an ADR before v0.14.0);
- how a third party replays when the raw responses never enter the public repository or supplement. The possible answers are private sharing where the terms allow, a re-run declared as such, or a restated v1.0 criterion (before v0.13.0, together with the providers' terms);
- whether DuckDB reads database files written by earlier versions for as long as a review must stay readable (before v0.5.0).

## What v1.0 means

v1.0 means that the central promise of a systematic review holds on real data: the search and the screening are reproducible and auditable. It is measured against a real review, not against fixtures written for the test.

What LRCC cannot guarantee is written down rather than implied. A re-run is not a replay, because databases grow. A single human reviewer is a declared limitation, not a solved one.

## The review does not wait for the software

If the first real review cannot wait for LRCC, it is done by hand, and v1.0 is measured on the next one.

## After v1.0: direction, not commitment

- **v1.x, the window.** A CustomTkinter window over the same slices: first it reads (status, diagram, records), then it screens. No listening port, and the window decides nothing.
- **v2.x, prioritization.** The featurizer port is born with three real cases: TF-IDF, SPECTER2, and embeddings served by Ollama over the private network. It is evaluated by retrospective simulation on the labels of a completed review, with several seeds, and a decision record chooses by evidence. It is used prospectively on later reviews, with people still screening every record. No vector database: at thousands of records, exact similarity costs milliseconds, and embeddings live as columns next to their records. Also in this range: automated citation searching (OpenAlex), open-access locations and search updates.
- **v3.x, suggestions.** A local language model suggests a decision with a criterion code, quoting the sentence of the abstract that justifies it; the quotation is verified mechanically, and any precedents retrieved from earlier decisions are recorded with the suggestion. The model suggests; it never decides.

## Out of scope

Downloading PDFs. Scraping search engines. A language model inside the deterministic pipeline. A listening port. Data extraction from full texts, which belongs to LACC.

## On the LACC side

Two decisions belong to LACC rather than to this repository: an ADR that re-scopes LACC's planned `discover` capability to importing LRCC bundles, and a skill for structured extraction with a verified quotation behind every value.
