# Chapter 1 - Architecture

This chapter describes how LRCC's code is laid out and what enforces the layout. It describes what
exists; where something is still planned, it says so. The decisions behind it are:

- ADR-0003, layout, amended by ADR-0010;
- ADR-0004, storage;
- ADR-0005, integration;
- ADR-0006, workspace;
- ADR-0010, configuration and protocol.

## Status

As of v0.9.0 every layer holds code. There are three ports:

- the source port, with PubMed, arXiv, Scopus and IEEE Xplore behind it;
- the store port, with each review's DuckDB database behind it;
- the catalog port, with the workspace's work catalog behind it.

Every request goes through one HTTP client. A search can also enter a review as a database's
RIS export, imported as a run. Records are joined into works by exact deduplication.

## The layout

```
src/lrcc/
├── domain/
│   ├── errors.py       LrccError and its kinds; validation failures as plain lines
│   ├── documents.py    YAML read once, with safe_load, into a mapping
│   ├── identifiers.py  review_id, validated before it becomes a folder name
│   ├── config.py       Config: the workspace path, absolute and required
│   ├── protocol.py     Protocol format 1, and the digest over the file's bytes
│   ├── workspace.py    Workspace: the boundary of ADR-0006
│   ├── reviews.py      read a review's protocol from the workspace
│   ├── record.py       Record, RawResponse and SearchResult: what a source said
│   ├── runs.py         Run, and the hash chain of the run log
│   ├── ris.py          the RIS reader: a database's export into records
│   ├── works.py        Work, identifiers, work_id, and the exact linking of records
│   ├── fuzzy.py        candidate pairs by title, a person's decisions, their chain, groups
│   ├── pairs_csv.py    the candidate pairs as a CSV file, written and read back
│   ├── gold.py         GoldSet: works known to be relevant, and their identifiers
│   └── secrets.py      API keys from the .env beside the configuration, never shown
├── ports/
│   ├── source.py       the source port: a query and a limit in, a SearchResult out
│   ├── store.py        the store port: the run log, records, raw responses and links
│   └── catalog.py      the catalog port: every work of the workspace and its identifiers
├── adapters/
│   ├── http.py         the one HTTP client: allowlist, rate limit, retries
│   ├── sources/        pubmed.py, arxiv.py, ieee.py, scopus.py; safe_xml.py, safe_json.py
│   └── storage/        duckdb_store.py: one database per review, responses as files;
│                       duckdb_catalog.py: the workspace's work catalog
├── features/
│   ├── configuration.py  read the configuration, open its workspace
│   ├── init/             create a review from the synthetic protocol template
│   ├── validate.py       check a protocol and report its digest
│   ├── search.py         run the protocol's string on one source: a stored run, or a preview
│   ├── imports.py        store a database's RIS export of the string as a run
│   ├── dedupe.py         join records into works; list candidate pairs; record decisions
│   ├── status.py         list a review's runs and verify its log
│   ├── check_query.py    test a string against the gold set: retrieved, missed, not indexed
│   ├── verify.py         check every stored response and record against the log
│   └── replay.py         rederive every run's records from its stored responses
└── views/
    └── cli/
        ├── app.py          the `lrcc` command (Typer and Rich)
        └── composition.py  builds the HTTP client, a source, a store and the catalog
```

The hexagon (`domain`, `ports`, `adapters`) is horizontal and shared: one `Record`, one hash
chain, one HTTP client. Each capability is a vertical slice under `features/`, holding its own use
case, so "how does deduplication work" is answered by one folder.

## Who may import whom

| Layer | May import |
|---|---|
| `domain` | the standard library, Pydantic and PyYAML; nothing else in `lrcc` |
| `ports` | `domain` |
| `adapters` | `domain`, `ports` |
| `features` | `domain`, `ports`, and its own slice; never `adapters`, never another feature |
| `views` | `features` and `domain`; `adapters` only in a module named `composition` |

A feature receives its adapters and never builds them. The view is the driving adapter, so it
builds concrete adapters from the configuration in its `composition` module and hands them over.
Logic two features need moves down into `domain`; it is never imported sideways. That rule is why
the domain parses YAML: both the configuration and the protocol are YAML documents (ADR-0010).

Nothing anywhere may import LACC's package: the two programs meet only through the review bundle
(ADR-0001).

## How a command runs

`lrcc validate example --config C:\lrcc\config.yaml` goes through these steps:

1. **The view parses the arguments.** Typer takes `--config`, or reads `LRCC_CONFIG` when the
   flag is absent. The view passes the path and the environment to
   `features.configuration.open_configured_workspace`.
2. **The configuration is read and validated once** (`domain.config`). Then the workspace is
   opened, and refused if it lies in a repository or a synchronised folder (`domain.workspace`).
3. **The view calls the feature** with the workspace: `features.validate.validate_review`. The
   feature resolves the protocol's path inside the boundary, parses the file's bytes into a
   frozen `Protocol`, and returns a result carrying the digest of those bytes.
4. **The view renders the result.** It prints it as text or, with `--json`, as data. If any step
   raised an `LrccError`, the view prints the error's message and details and exits with code 1,
   without a traceback.

Content that comes from files is rendered as plain text, never as Rich markup.

## A view decides nothing

A view parses input and renders output. The rule is checked by what presentation looks like,
because logic has no syntax. A function in a view is presentation if it uses the presentation
vocabulary (Rich's `Console`, `Table`, `Panel`, `Progress`, prompts, Typer), directly or through
a function it calls. Anything else is logic that belongs in a feature. There are three named
exemptions:

- Typer commands, recognised by their decorator;
- the entry point, `main`;
- the `composition` module.

## API keys

Keys come from the `.env` in the folder that holds the configuration file, and from nowhere
else; a variable already set in the environment wins (ADR-0015). A source asks for its key
only when it makes a request, so a replay, which makes none, needs no key.

The one HTTP client keeps keys out of everything LRCC stores:

- a key sent as a query parameter is recorded as `[redacted]`;
- a key sent as a header is not recorded at all;
- an answer that repeats a key is refused, because a stored answer is kept byte for byte;
- the start of an error answer is quoted with every key replaced.

## What enforces it

`tests/test_layering.py` reads every module with `ast`, without importing it, and checks:

- that every module lives in one of the five layers;
- every import against the table above;
- every view function against the presentation rule.

Parametrized cases write a temporary package that breaks each rule and assert the test names the
break. A check that has never been seen to fail is not trusted.

`tests/test_no_listening_port.py` checks another structural promise: LRCC contains no
server-side networking (ADR-0005).

`tests/test_egress.py` checks the third: only `adapters/http.py` may import a networking
library, so the allowlist in that one client is the only way out (ADR-0011). The client refuses
a request before sending it when the network is off, when the host is not listed, or when the
address is not plain HTTPS, and it never follows a redirect.

## What a run leaves behind

```
library/
└── catalog.duckdb                     every work of the workspace, and its identifiers
reviews/<review_id>/
├── protocol.yaml
├── review.duckdb                      the run log, the records, each record's work, decisions
└── runs/
    └── 0001-20260930T141500Z-pubmed/
        ├── response-0001.raw          each answer, byte for byte
        └── response-0002.raw
```

A log entry is one canonical JSON document. It names each response file with its size and
SHA-256, and its own hash covers the entry and the hash of the entry before it (ADR-0012).
`lrcc status` recomputes that chain every time it is run.

## Replay uses the code that searched

Each source derives its records in one method, `records_from`, which takes the raw answers of
a search and makes no request. `search` calls it on the answers it just received, and
`replay` calls it on the answers a run stored. They cannot disagree about how an answer is
read, so a replay that differs from its run means the code changed since (ADR-0013).

`lrcc verify` asks the other question: whether the files and the records on disk are still
the ones the log describes. Neither command writes anything.

## An import is a run too

When a search goes through a database's web interface, `lrcc import` stores the RIS files it
exported as a run (ADR-0016). Each file is stored like an answer, in the same log, and the entry
adds the day of the search. `replay` reads those files with the RIS reader in `domain/ris.py`,
the same code the import used. The reader sits in the domain because two features use it, and
a feature never imports another.

A field added to the log entry after v0.7.0 is optional, and is left out while empty. The
entries of earlier versions keep their canonical form, and their chain still verifies.

## Records become works

`lrcc dedupe` joins records into works through the identifiers they share: a DOI, a PMID, an
arXiv identifier, or a database's own number (ADR-0017). The linking is a pure function in
`domain/works.py`. It takes the records in log order and the identifiers already known, so the
same records always give the same works.

Identity is workspace-wide, because a work can belong to several reviews (ADR-0006):

- `library/catalog.duckdb` holds every `work_id` and every identifier, one work per identifier;
- each review's database holds only its links: which work each record joined, and why.

The catalog is written first, so a pass interrupted between the two leaves only identifiers that
the next pass finds again.

What no identifier joins, a person may (ADR-0018). `lrcc candidates` lists the pairs of works
whose titles score 0.80 or more. `lrcc decide` reads back the CSV file the person filled, and
appends each `same` or `different` to a second hash-chained log in the review's database,
attributed to the configuration's `reviewer`. Works joined by `same` form a group, the unit the
review counts. Groups stay in the review: the catalog never merges two `work_id`s.

The three commands are one slice, `features/dedupe.py`, because they share the loading of a
review and its checks. Comparing every pair of titles is the one slow step, so only
`candidates` does it.

## Planned

- **Screening (v0.10.0):** title and abstract decisions on each group, in the same kind of
  hash-chained log.
- **Integration (ADR-0005, from v0.14.0):** the review bundle, `--json` on every command, and
  the public Python API in `lrcc.api`.
