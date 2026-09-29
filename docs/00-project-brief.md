# Chapter 0 - Project brief

This chapter was written on 2026-09-28, before the first line of code. It records the founding design of LRCC. Where a later chapter or a decision record disagrees with it, the later document wins, and a note is added here instead of the text being quietly rewritten.

Notes are blockquotes that begin with their date. The first ones were added on 2026-09-29, when the decision records ADR-0001 to ADR-0009 were drafted (status: Proposed) and reading this brief against them exposed gaps. A note that cites a Proposed record describes a proposal, not a decision. All nine records were accepted by the maintainer later that day, unchanged.

## 1. Purpose

LRCC, the Literature Review Control Center, makes the identification and screening stages of a literature review reproducible and auditable. It runs versioned search strings against bibliographic databases, keeps what each source returned, deduplicates records, supports human screening of titles, abstracts and full texts, tracks which full texts were obtained, reports PRISMA 2020 counts, and exports a versioned review bundle that is ready for data extraction.

The promise is narrow on purpose: every number in a flow diagram can be traced to a stored response and a recorded decision, and a third party can reproduce those numbers.

The name follows its sibling, LACC (Local AI Control Center). LRCC is the control center of a review's process: protocol, search, screening, PRISMA counts and the review bundle. LACC is the workbench for the review's content. In a publication, LRCC is defined at its first use, in the abstract and in the body, and cited by the DOI of the exact release used.

## 2. Who it is for

- Researchers running systematic or scoping reviews whose search and screening have to survive peer review and replication.
- Tools built on top of it. The review bundle is a published contract; LACC is its first consumer, not its owner.

LRCC was motivated by a master's thesis that needs several reviews. The first real review is the measuring stick for v1.0.

## 3. Scope

LRCC does:

- run versioned search strings against PubMed, arXiv, Scopus and IEEE Xplore, or import their manual exports;
- validate a search string against a gold set of works known to be relevant;
- import records identified by other methods, such as citation searching;
- deduplicate exactly and fuzzily, recording every merge and its reason;
- support title/abstract screening and full-text eligibility, with coded reasons, as append-only decisions;
- track full-text retrieval against a local library of PDFs that it never downloads and never opens;
- report PRISMA 2020 counts and document the search following PRISMA-S;
- export a review bundle.

LRCC does not, by design:

- download PDFs: access is often institutional, and obtaining a text is a human step;
- scrape search engines: it is against their terms, and it is not reproducible;
- put a language model inside the deterministic pipeline;
- open a listening port;
- extract data from full texts: that is LACC's work;
- decide anything a person must decide;
- keep licensed content in its public repository.

## 4. The workflow, from idea to extraction-ready

1. **Idea, question, protocol.** The question gets an explicit framework (for a scoping review, Population-Concept-Context, reported with PRISMA-ScR). The protocol fixes coded eligibility criteria (INC/EXC), sources and extraction fields before any search. Registering the protocol publicly (OSF, for instance; PROSPERO does not register scoping reviews) together with its hash lets anyone check that the search used what was registered. `lrcc init` creates a review from a template. Protocols live in the workspace, never in this repository.
2. **The search string, validated.** Concept blocks with synonyms, tested with `lrcc check-query` against a gold set; each version is hashed. The usual failure is terminology: part of a field may name itself with words the string does not contain. Ideally a librarian reviews the string using the PRESS guideline.
3. **Execution.** `lrcc search` per source. Raw responses are kept; each run is logged with its date, the count the source reported and the count retrieved.
4. **Deduplication.** `lrcc dedupe`: exact first, then fuzzy with human confirmation.
5. **Title/abstract screening.** `lrcc screen`. A pilot calibrates the criteria; a change after the pilot is a versioned amendment of the protocol, never a silent edit. Uncertain records go on to full text.
6. **Full-text retrieval.** `lrcc retrieve` lists what to obtain, with the links already known (arXiv, PMC). A person obtains the texts through institutional access, interlibrary loan or the authors, and `lrcc scan` registers what arrived. What could not be obtained is recorded with a reason, and PRISMA 2020 counts it.
7. **Full-text eligibility.** `lrcc fulltext`, with coded reasons.
8. **Other methods.** Backward and forward citation searching on the included works; the records are imported and counted in the second column of the PRISMA 2020 diagram.
9. **Close.** `lrcc report` and `lrcc export`. Extraction continues in LACC.

## 5. Relationship with LACC

LRCC is a sibling of LACC (local-ai-control-center), not a capability inside it:

- **Exposure.** LRCC needs API keys and makes many requests to external services. Keeping that surface out of the tool that holds private research material is the cheapest way not to expose that material.
- **A bounded context of its own.** Reproducible search, deduplication, auditable screening and flow-diagram accounting are a domain with its own rules. LRCC does not write; it makes sure the corpus is complete and documented.
- **Complementarity.** A gap measured over an incomplete corpus is a false gap. A systematic search is what makes a corpus complete, so LRCC supplies the precondition that coverage measurements in LACC need.

LRCC finds and screens; LACC verifies and writes. The contract between them is the review bundle. LACC imports it as its acceptance step: everything that arrives is treated as hostile until accepted. Structured extraction with a verified quotation behind each value is a LACC capability.

## 6. Architecture

- **A shared, horizontal hexagon:** `domain/` (entities and rules), `ports/` (protocols), `adapters/` (sources, storage, notification).
- **Vertical slices** under `features/`, one per capability: init, check-query, search, import, replay, verify, dedupe, screen, retrieve, scan, fulltext, report, export, status.
- **Views decide nothing:** the CLI (Typer and Rich) now, a window (CustomTkinter) after v1.0. `tests/test_layering.py` checks both directions: dependencies point inward, and no logic leaks outward into a view.
- **Ports only with two real cases.** The source port starts with PubMed and arXiv. There is no storage port. The featurizer port arrives after v1.0, together with its real cases.
- **Verify at the boundary, then trust:** frozen Pydantic models where data enters.
- **One HTTP client** (httpx) with a host allowlist, retries with backoff (tenacity) and per-source rate limits from configuration. XML is parsed with defusedxml.
- **Storage:** one DuckDB database per review, raw responses stored for replay, exports as CSV, Parquet or JSON.
- **Replay versus re-run:** a replay rederives everything from stored responses and must produce identical outputs; a re-run queries the source again and is documented as a new run, because databases grow.
- Every command runs non-interactively with flags and offers `--json`. Screening is the only interactive step.

Sketch of the repository:

```
literature-review-control-center/
├── pyproject.toml  uv.lock  .python-version
├── .env.example  .pre-commit-config.yaml  run.ps1
├── README.md  PRINCIPLES.md  VISION.md
├── CHANGELOG.md  CITATION.cff  LICENSE
├── schemas/            # JSON Schema of the review bundle, versioned
├── examples/           # one synthetic example review
├── src/lrcc/
│   ├── domain/
│   ├── ports/
│   ├── adapters/       # sources/, storage/, notify/
│   ├── features/       # one vertical slice per capability
│   └── views/          # cli/ now, window/ after v1.0
├── tests/              # unit/, integration/, fixtures/, test_layering.py
├── docs/               # numbered chapters, adr/, guides/, api/
└── .github/workflows/
```

> **2026-09-29.** The sketch originally listed an AI coding assistant's instruction file and settings folder at the repository root. They were removed: under ADR-0008 the repository carries no assistant-specific files, and those files live in the maintainer's private folder next to the checkout. `run.ps1` was added: under ADR-0002 it keeps the virtual environment outside synchronised folders, as in LACC.

## 7. Records, works and states

A **record** is one hit from one source. A **work** is one publication, which may appear as several records (several databases, or a preprint and its published version). Deduplication maps records to works: normalized DOI first, then cross identifiers (PMID, arXiv ID), then normalized titles with fuzzy matching whose threshold is measured on real data. The published version is kept over the preprint, every merge is logged with its reason, and fuzzy merges are confirmed by a person.

Each work in a review moves through these states: identified, deduplicated, screened (included, excluded with a code, or uncertain), sought for retrieval, retrieved or not retrieved (with a reason), assessed for eligibility, and finally included or excluded (with a reason). Every transition records who, when and why. PRISMA counts are queries over these states; nothing is counted by hand.

A decision records the decision, the criterion code, the reason, who decided (a person; after v1.0 a model may add a suggestion, recorded with its version, but never a decision) and the time. Decisions are hash-chained; a correction is a new entry, never an edit.

## 8. The library of full texts

- The workspace root lives outside any git working tree and holds `library/<work_id>/` and `reviews/<review_id>/`.
- **One folder per work, never per topic.** A work can belong to several topics and several reviews; topics are metadata, not locations. A work shared by two reviews is stored once.
- **`work_id`** is deterministic and safe on every filesystem: first author, year and a short hash of the normalized DOI (or PMID, or arXiv ID), in lowercase ASCII `[a-z0-9-]`, for example `dou2020-3f9a2c`.
- A work folder holds `fulltext.pdf` and, when they exist, `supplement-1.pdf` and so on.
- **`lrcc scan` is read-only.** It checks that a file really is a PDF, enforces a size ceiling, computes its SHA-256 and records where it came from (institutional access, open access, author, interlibrary loan). It never opens the content and never moves or renames anything: for a misplaced file it prints the command, and a person runs it.
- Eligibility decisions are bound to the digest of the exact PDF that was read.
- Whether LACC points its workspace at the same root is decided by an ADR before v0.14.0.
- Backups go to hardware the user owns, over the private network, not to a third-party cloud.

> **2026-09-29, from ADR-0006 (Proposed).** Read against the rest of this brief, the `work_id` above has four gaps:
>
> - works with no DOI, PMID or arXiv ID;
> - a missing or non-ASCII author, or a missing year;
> - collisions in a six-digit hash;
> - an identifier that changes when a preprint merges into its published version. Recomputing the `work_id` would then force a folder rename, which `scan` forbids.
>
> The proposal:
>
> - a `work_id` is **assigned once and never recomputed**;
> - later identifiers become aliases, held in a workspace-level catalog (`library/catalog.duckdb`) that enforces one work per identifier;
> - collisions stop with an error;
> - works without an identifier hash a normalized title and year and are flagged.
>
> The workspace is also refused under a synchronised cloud folder that can be detected (OneDrive), because that would copy licensed PDFs to a third party, against the last bullet above.

## 9. The review bundle

The bundle is the contract. It contains a manifest (format version, LRCC version and git SHA, UTC timestamp, a digest of every file), the protocol snapshot with its hash (search strings, criteria, extraction schema), the search provenance, the included works with their identifiers, every decision with the head of the hash chain, the work-to-PDF map with digests, and the PRISMA counts. Its JSON Schema is published under `schemas/` and versioned with SemVer.

LRCC offers three surfaces: the bundle, the CLI with `--json`, and a documented public Python API covered by SemVer. There is no HTTP server. If a real client ever needs one, it arrives with its own ADR, off by default and bound to the private network interface.

> **2026-09-29, from ADR-0005 (Proposed).** The public Python API is confined to one module, `lrcc.api`; everything else under `lrcc` is internal. The content of the bundle is decided in its own record before v0.14.0; the list above is direction.

## 10. Security and exposure

Approximation is a tool for performance, never for exposure. Controls on exposure refuse rather than warn.

- **Egress:** only hosts named in the configuration are contacted; a test in the quality gate fails if anything else is; no environment variable can widen the list.
- **Workspace:** outside any git working tree, or refused; every path is resolved and checked against the boundary.
- **Secrets:** only in `.env`, never in YAML, never logged; `.env.example` is versioned without values; gitleaks runs in pre-commit; GitHub push protection is on.
- **Untrusted input:** API responses, titles, abstracts, author strings, PDFs, fixtures and imported files. Defenses: defusedxml, parameterized SQL, sanitization of formula-leading cells in CSV exports, identifiers instead of titles for paths, size ceilings.
- **Content is data, never instructions**, for any model that reads it, coding agents included.
- **Notifications** carry counts, never titles or abstracts.
- **No listening port.**

## 11. Data and licensing

- Raw responses, abstracts and PDFs never enter the public repository.
- Test fixtures are synthetic or trimmed, and a person reviews them before they are committed.
- The public supplement of a paper carries search strings, identifiers, decisions, reasons and counts, not licensed text.
- What each provider's terms allow is a premise to verify (see chapter 2).

> **2026-09-29.** This section and the v1.0 criterion pull against each other. v1.0 asks that "a third party reproduces its counts by replay from a clean install". A replay reads stored raw responses, and this section keeps raw responses out of the public repository and the public supplement. A third party therefore cannot replay from public material alone. It is recorded as a premise in chapter 2, to be settled before v0.13.0 together with the providers' terms. The possible answers are:
>
> - raw responses are shared privately, where the terms allow;
> - the third party re-runs, which is a different thing from a replay;
> - the criterion is restated.

## 12. Infrastructure

- A private Tailscale network. Long runs may execute on the desktop over Tailscale SSH. After v1.0, Ollama on the desktop GPU serves embeddings and a local model.
- A self-hosted ntfy server announces finished runs, with counts only.
- No third-party service is contacted except the bibliographic APIs named in the configuration.

## 13. Quality and tooling

- **uv:** packaged application, `src` layout, lockfile committed, Python version pinned.
- **ruff** for linting and formatting (docstring rules in Google style, security rules), **mypy** in strict mode, **pytest** with coverage; HTTP fixtures with respx.
- **pre-commit:** ruff, mypy, gitleaks, and a commit-msg hook that rejects AI attribution trailers.
- **CI:** GitHub Actions on Linux and Windows.
- **Releases:** SemVer, Keep a Changelog, one tag per version, each release archived on Zenodo with a DOI; `CITATION.cff`.
- **License:** MIT, like LACC, to be confirmed by ADR.

> **2026-09-29, from ADR-0002 and ADR-0009 (Proposed).**
>
> - **Python:** 3.12 pinned, with 3.12 as the floor.
> - **Build:** the `uv_build` backend.
> - **Gate:** exactly `ruff check`, `ruff format --check`, `mypy` and `pytest`.
> - **Coverage:** reported from v0.0.1; its threshold is fixed with the first real code.
> - **Virtual environment:** kept out of synchronised folders through `run.ps1`.
> - **License:** MIT for everything in the repository.

## 14. Documentation

- Root: `README.md` with an honest status, `PRINCIPLES.md`, `VISION.md`.
- Numbered chapters in `docs/`: 00 brief, 01 architecture, 02 roadmap, and a chapter on the search method that doubles as supplementary material for papers.
- `docs/adr/`: one decision per record, MADR format, written before the code it governs.
- `docs/guides/`: the development guide (how a phase is done, adding a source, recording fixtures, releasing) and the usage and operations guides (first review, API keys, replay, backups, day-to-day running).
- `docs/api/`: generated from docstrings.

A change is not done until its documentation is true.

> **2026-09-29, from ADR-0002 (Proposed).** Generating `docs/api/` needs a generator, which means a dependency and a decision. The generator is deferred to its own record before v0.14.0, when the public Python API exists; until then there is nothing public to document. The roadmap's v0.0.1 row was amended to match.

## 15. Language

Everything public is in English: code, docstrings, documentation, CLI messages, commits. Private notes in Spanish live outside the repository. There is no Spanish mirror of the documentation: a translation that lags behind is a false statement.

## 16. Working with an AI coding assistant

> **2026-09-29.** This section originally named the assistant, its instruction file and its settings folder. It was rewritten in general terms because, under ADR-0008, the public repository carries no assistant-specific files and names no AI tool as an author. The assistant's operating instructions and permission settings exist, and live in the maintainer's private folder next to the checkout. What follows is the method, which does not depend on a vendor.

Agentic inside a phase, with defined stops, and a person as the gate between phases. The operative rules are in the assistant's operating instructions, kept outside the repository. In short:

- **The agent proceeds** within the phase scope: implementation, tests, the quality gate, drafts of documentation.
- **The agent stops and asks** before dependencies, guardrail changes, weakening the gate, credentials or real network access, fixtures from real APIs, moving, deleting or renaming files, and any work outside the scope.
- **Only a person** decides ADRs, screens, changes protocols, runs real searches, pushes, tags, releases, mints DOIs, changes the principles and accepts phases.

The cycle of a phase: an ADR decided by a person; a fresh session with the operating instructions and that ADR as context; plan mode; implementation on the phase branch in small commits; a pull request; a review of the diff that asks of every CHANGELOG claim what in the program sets it; the phase's real scenario; merge and tag by a person.

Enforcement comes in layers, because instructions shape what an agent tries but do not limit what it can do: permission rules in the assistant's settings (ask before moving, deleting or pushing; deny reading `.env` and the real workspace); a hook that inspects full commands before they run; and the sandbox, which on Windows means WSL2. There, filesystem isolation is the dependable part (network isolation has been reported as unreliable), so LRCC's own egress allowlist remains the network enforcement. Sessions never run with permission checks bypassed. Commit attribution is disabled in the assistant's settings and rejected by the commit-msg hook and by CI (ADR-0008).

The most important guardrail is not a setting: the agent never touches the real workspace. It works against temporary workspaces and a development workspace with synthetic data.

| Autonomy | Versions | Why |
|---|---|---|
| The agent proceeds within scope | v0.0.1, v0.4, v0.7, v0.14 (once the schema is decided) | mechanical work with objective verification |
| The agent writes; a person reviews line by line | v0.1, v0.2, v0.3 | security boundaries: a mistake there is exposure |
| The agent builds with synthetic data; a person validates with real data | v0.5, v0.6, v0.8 to v0.13, v0.15 | keys, real network, thresholds, methodological judgment, real data |
| A person only | v1.0 | the test against a real review |

## 17. Decisions to record in v0.0.1

- [ADR-0001](adr/ADR-0001-lrcc-is-a-sibling-of-lacc.md): LRCC is a sibling of LACC, not LACC's `discover`.
- [ADR-0002](adr/ADR-0002-packaging-and-toolchain.md): packaging and toolchain (uv, `src` layout, Python version, the quality gate).
- [ADR-0003](adr/ADR-0003-shared-hexagon-and-vertical-slices.md): architecture (shared hexagon, vertical slices, views without logic, layering tests in both directions).
- [ADR-0004](adr/ADR-0004-one-duckdb-database-per-review.md): storage (one DuckDB database per review, no storage port).
- [ADR-0005](adr/ADR-0005-integration-by-contract.md): integration by contract (review bundle, CLI `--json`, public Python API; no listening port).
- [ADR-0006](adr/ADR-0006-workspace-library-and-work-id.md): workspace and library layout, and `work_id`.
- [ADR-0007](adr/ADR-0007-language-and-naming.md): language policy and naming (LRCC, and how publications define and cite it).
- [ADR-0008](adr/ADR-0008-no-ai-co-authorship.md): no AI co-authorship in commits; disclosure of AI use in publications.
- [ADR-0009](adr/ADR-0009-license.md): license.

> **2026-09-29.** All nine were drafted as Proposed, each with its options and trade-offs; a person decides them. Drafting them surfaced the notes added throughout this chapter.

Open premises are listed in chapter 2.
