# Decision records

One decision per record, in [MADR](https://adr.github.io/madr/) format, written before the code it
governs. The number is the identity: records are cited by it from docstrings and chapters.

Each record lays out:

- the options that were considered;
- the strongest objection to the one chosen;
- what in the program confirms it.

When a record is built, it gains an "Implementation" section saying what the code actually does,
including any detail settled while building it.

**Status** moves from `proposed` to `accepted` when the maintainer decides, and gains "built in
vX" when the code exists. A record that is later replaced is marked `superseded by ADR-NNNN`,
never deleted or rewritten.

| Record | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-lrcc-is-a-sibling-of-lacc.md) | LRCC is a sibling of LACC, coupled only by the review bundle | accepted |
| [ADR-0002](ADR-0002-packaging-and-toolchain.md) | uv package, Python 3.12, the four-command gate, the environment outside the checkout | built in v0.0.1; coverage threshold in v0.1.0 |
| [ADR-0003](ADR-0003-shared-hexagon-and-vertical-slices.md) | Shared hexagon, vertical slices, views that decide nothing, checked both ways | built in v0.0.1; amended by ADR-0010 |
| [ADR-0004](ADR-0004-one-duckdb-database-per-review.md) | One DuckDB database per review, raw responses as files, no storage port | built in v0.5.0; amended by ADR-0012 |
| [ADR-0005](ADR-0005-integration-by-contract.md) | Bundle, `--json` and `lrcc.api`; no listening port | accepted |
| [ADR-0006](ADR-0006-workspace-library-and-work-id.md) | Workspace outside any repository, one folder per work, an immutable `work_id` and a work catalog | boundary built in v0.1.0 |
| [ADR-0007](ADR-0007-language-and-naming.md) | English for everything public; names; citing the version DOI | accepted |
| [ADR-0008](ADR-0008-no-ai-co-authorship.md) | No AI co-authorship, enforced by hook and CI; disclosure in publications | built in v0.0.1 |
| [ADR-0009](ADR-0009-license.md) | MIT for everything in the repository | built in v0.0.1 |
| [ADR-0010](ADR-0010-configuration-protocol-and-workspace.md) | Configuration, protocol and workspace in one phase, with `init` and `validate` | built in v0.1.0 |
| [ADR-0011](ADR-0011-one-http-client-and-the-first-two-sources.md) | One HTTP client with an allowlist, PubMed and arXiv, and `lrcc search` | built in v0.3.0 |
| [ADR-0012](ADR-0012-stored-runs-and-a-hash-chained-log.md) | A search is a stored run: raw responses, records and a hash-chained log | built in v0.5.0 |
| [ADR-0013](ADR-0013-verify-and-replay.md) | `verify` checks what is stored; `replay` rederives it offline; PubMed book records | built in v0.7.0 |
| [ADR-0014](ADR-0014-checking-a-search-string-against-a-gold-set.md) | A search string is checked against a gold set, with coverage kept apart from misses | proposed; built in v0.7.0 |
| [ADR-0015](ADR-0015-api-keys-scopus-and-ieee-xplore.md) | API keys from a `.env` beside the configuration, never recorded; Scopus and IEEE Xplore | proposed; built in v0.8.0 |
