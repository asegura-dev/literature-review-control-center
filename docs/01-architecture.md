# Chapter 1 - Architecture

This chapter describes how LRCC's code is laid out and what enforces the layout. It describes what
exists; where something is still planned, it says so. The decisions behind it are:

- ADR-0003, layout, amended by ADR-0010;
- ADR-0004, storage;
- ADR-0005, integration;
- ADR-0006, workspace;
- ADR-0010, configuration and protocol.

## Status

As of v0.1.0 the domain, three features and the command-line view hold code. `ports/` and
`adapters/` are still empty: no external system is reached yet.

## The layout

```
src/lrcc/
├── domain/
│   ├── errors.py       LrccError and its kinds; validation failures as plain lines
│   ├── documents.py    YAML read once, with safe_load, into a mapping
│   ├── identifiers.py  review_id, validated before it becomes a folder name
│   ├── config.py       Config: the workspace path, absolute and required
│   ├── protocol.py     Protocol format 1, and the digest over the file's bytes
│   └── workspace.py    Workspace: the boundary of ADR-0006
├── ports/              protocols, only where two real implementations exist (none yet)
├── adapters/           sources/, storage/, notify/ (planned)
├── features/
│   ├── configuration.py  read the configuration, open its workspace
│   ├── init/             create a review from the synthetic protocol template
│   └── validate.py       check a protocol and report its digest
└── views/
    └── cli/app.py      the `lrcc` command (Typer and Rich)
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

## What enforces it

`tests/test_layering.py` reads every module with `ast`, without importing it, and checks:

- that every module lives in one of the five layers;
- every import against the table above;
- every view function against the presentation rule.

Parametrized cases write a temporary package that breaks each rule and assert the test names the
break. A check that has never been seen to fail is not trusted.

`tests/test_no_listening_port.py` checks the other structural promise: LRCC contains no
server-side networking (ADR-0005).

## Planned

- **HTTP and identity (v0.3.0):** one HTTP client with an allowlist, a frozen `Record`, and
  `work_id` with its catalog (ADR-0006).
- **Sources (from v0.4.0):** the source port, shaped by its two real cases, PubMed and arXiv.
- **Storage (ADR-0004, from v0.5.0):**
  - one DuckDB file per review, raw responses stored as files beside it with their SHA-256;
  - no storage port.
- **Integration (ADR-0005, from v0.14.0):** the review bundle, `--json` on every command, and
  the public Python API in `lrcc.api`.
