# Chapter 2 - Roadmap: where LRCC is and where it is heading

This chapter describes the route to v1.0 and the direction after it. Nearer phases are described with more confidence; later ones are direction, and are expected to change as real code reveals what each one needs. It is not a schedule and carries no dates.

## Status

This roadmap was written on 2026-09-28, before the first commit. The current phase is **v0.0.1, Scaffold**. On 2026-09-29 it was built on the branch `v0.0.1-scaffold`, where its gate is green locally on Windows. Two things remain before it is done: CI on Linux and Windows, observed after a push, and the maintainer's acceptance. What was run and observed is in [the phase notes](phases/v0.0.1.md). No capability exists yet.

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
| v0.1.0 | Configuration and review protocol: a frozen `Config` loaded from YAML, network off by default, allowed hosts, secrets only from `.env`; the review protocol in YAML (search strings per source, INC/EXC codes, extraction schema) with its hash; `init` creates a review from the synthetic example template | an empty required value is a clear error, never a silent default |
| v0.2.0 | Workspace with a boundary, outside any git working tree, holding `library/` and `reviews/<id>/` | a workspace inside a repository is refused, and so is a path that escapes the boundary |
| v0.3.0 | One HTTP client with a host allowlist, retries and per-source rate limits; defusedxml; a frozen `Record`; a deterministic `work_id`, assigned once, with later identifiers kept as aliases in a workspace-level catalog (ADR-0006) | the gate fails if anything touches an unlisted host |
| v0.4.0 | The source port with its two real cases, PubMed and arXiv, tested with recorded HTTP | `search` runs offline against fixtures |
| v0.5.0 | DuckDB store, raw responses kept, hash-chained run log, `status` with Rich; the first real run of the first review | real counts are recorded with their date and query version |
| v0.6.0 | `check-query`: a search string against a gold set, per source | the string retrieves the whole gold set, or every gap is recorded with its reason |
| v0.7.0 | `replay` and `verify` | a replay produces identical outputs; a re-run is documented as a different run |
| v0.8.0 | Scopus and IEEE Xplore (by API if a key exists, by importing manual exports otherwise); the same import serves records found by other methods; ntfy for long runs | four sources unified; a long run says when it is done |
| v0.9.0 | Exact and fuzzy deduplication, incremental, with a threshold measured on real data and a merge log | a new batch is deduplicated against what exists; fuzzy merges are confirmed by a person |
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
