# Chapter 1 - Architecture

This chapter describes how LRCC's code is laid out and what enforces the layout. It describes what
exists; where something is still planned, it says so. The decisions behind it are ADR-0003
(layout), ADR-0004 (storage) and ADR-0005 (integration).

## Status

As of v0.0.1 the layers exist and are empty. Nothing below "planned" has code yet.

## The layout

```
src/lrcc/
├── domain/      entities, value objects and rules; pure
├── ports/       protocols, only where two real implementations exist
├── adapters/    sources/, storage/, notify/ (planned)
├── features/    one slice per capability (planned: init, search, dedupe, screen, ...)
└── views/       cli/ now, window/ after v1.0 (planned)
```

The hexagon (`domain`, `ports`, `adapters`) is horizontal and shared: one `Record`, one hash
chain, one HTTP client. Each capability is a vertical slice under `features/`, holding its own use
case, so "how does deduplication work" is answered by one folder.

## Who may import whom

| Layer | May import |
|---|---|
| `domain` | the standard library and Pydantic; nothing else in `lrcc` |
| `ports` | `domain` |
| `adapters` | `domain`, `ports` |
| `features` | `domain`, `ports`, and its own slice; never `adapters`, never another feature |
| `views` | `features`; `adapters` only in a module named `composition` |

A feature receives its adapters and never builds them. The view is the driving adapter, so it
builds concrete adapters from the configuration in its `composition` module and hands them over.
Logic two features need moves down into `domain`; it is never imported sideways.

Nothing anywhere may import LACC's package: the two programs meet only through the review bundle
(ADR-0001).

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

- **Storage (ADR-0004, from v0.5.0):**
  - one DuckDB file per review, raw responses stored as files beside it with their SHA-256;
  - a workspace-level work catalog for identity (ADR-0006);
  - no storage port.
- **Sources (from v0.4.0):** the source port, shaped by its two real cases, PubMed and arXiv.
- **Integration (ADR-0005, from v0.14.0):** the review bundle, `--json` on every command, and
  the public Python API in `lrcc.api`.
