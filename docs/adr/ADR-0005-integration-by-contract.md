---
status: accepted
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0005 - Integration by contract: a review bundle, `--json` and a public Python API, with no listening port

## Context and Problem Statement

LRCC's output is consumed by people, scripts and other tools. LACC is the first such tool: it
imports a review's included works and their provenance to begin data extraction. How other
programs reach LRCC's results decides:

- what LRCC promises to keep stable;
- what it exposes to the network;
- how tightly its consumers depend on its internals.

This record decides which surfaces exist. It does not decide the content of the bundle, which
gets its own record when v0.14.0 is planned.

## Decision Drivers

- A consumer must be able to verify what it received without trusting or importing LRCC.
- No listening port: nothing on the machine or the network should be able to reach LRCC.
- Stability promises must be explicit, and small enough to keep.
- Every command must also serve scripts (non-interactive, machine-readable).

## Considered Options

1. **Three surfaces:** a versioned review bundle with a published JSON Schema; `--json` output on
   every command; a documented public Python API. No listening port.
2. A local HTTP API (bound to the loopback interface) that consumers query.
3. Consumers read the review's DuckDB file directly.
4. A public Python API only.

## Decision Outcome

Chosen option: **option 1**.

- **The review bundle is the contract.** It is a set of files with a manifest and a digest of
  every file. Its JSON Schema lives in `schemas/`, versioned with SemVer independently of the
  program. A consumer validates a bundle against the schema without importing `lrcc`.
- **`--json` on every command**, so that scripts never parse human-oriented output. The JSON
  shape of each command is documented with the command.
- **A public Python API**, confined to one module (`lrcc.api`). Only what that module exports is
  covered by SemVer; everything else under `lrcc` is internal and may change in any release.
- **No listening port.** LRCC opens no socket for listening, in any mode. If a real client ever
  needs a server, it arrives with its own record, off by default and bound to the private network
  interface.
- **Refused:** consumers reading `review.duckdb` directly. The database schema is internal
  (ADR-0004).

### Consequences

- Good, because LACC depends on a schema and a set of files, not on LRCC's code or database.
- Good, because there is no network attack surface to defend.
- Good, because the stability promise is small: one schema, one module, the `--json` shapes.
- Bad, because there is no live query surface. A consumer that wants fresh data must run a
  command or re-export.
- Bad, because three surfaces must be documented and kept consistent with each other. In
  particular, the JSON of a command and the same data inside a bundle can drift.
- Bad, because before v1.0.0 SemVer allows breaking changes in any minor release. The promise is
  honest only from v1.0.0 on, and the CHANGELOG must name every break before then.

### Confirmation

- A test in the gate scans `src/lrcc/` and fails on server-side networking: `socket.bind`,
  `listen`, `http.server`, `socketserver`, `asyncio.start_server`, or a web framework import.
- From v0.14.0: a test consumer validates a bundle against `schemas/` without importing `lrcc`.
- From v0.14.0: every command has a test for its `--json` output.

## Pros and Cons of the Options

### Option 1 - Bundle, `--json`, public API

- Good, because the consumer can verify without trust, and nothing listens.
- Bad, because the data is exported, not queried, and three surfaces need documentation.

### Option 2 - Local HTTP API

- Good, because consumers get live queries, and any language can use it.
- Bad, because it opens a port. Even on loopback, any local process can reach it, and it would
  need authentication, and a record for each of those.
- Bad, because it contradicts a founding scope decision (the brief, section 3).

### Option 3 - Direct database reads

- Good, because it needs no export step.
- Bad, because consumers couple to an internal schema and to DuckDB's file format. They also read
  data that has not passed through a manifest or a digest.

### Option 4 - Python API only

- Good, because it is the least to document.
- Bad, because consumers must be written in Python and must import LRCC, which is exactly the
  coupling the bundle avoids, and which makes "validate without importing" impossible.

## More Information

- The brief, section 9, lists what the bundle is expected to contain. That list is direction; the
  bundle's schema is decided in its own record before v0.14.0.

## Implementation

- **v0.0.1.** `tests/test_no_listening_port.py` scans `src/lrcc/` and fails on server-side
  imports (`http.server`, `socketserver`, web frameworks) and on `bind`, `listen`,
  `start_server`, `create_server` and `serve_forever` calls. Parametrized cases prove each kind
  is caught, and one proves a client socket is not. The bundle, `--json` and `lrcc.api` arrive
  with their versions.
