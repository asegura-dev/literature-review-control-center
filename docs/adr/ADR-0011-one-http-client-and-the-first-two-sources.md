---
status: accepted (built in v0.3.0)
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0011 - One HTTP client, the first two sources, and `lrcc search`

## Context and Problem Statement

The roadmap put the HTTP client, the `Record` and `work_id` in v0.3.0, and the PubMed and arXiv
sources in v0.4.0. An HTTP client with no source to call delivers nothing a person can run, and
its rules (allowlist, rate limits, retries) are shaped by the sources that use it.

`work_id` names a work, and works first exist when records are deduplicated (v0.9.0). Building it
and its catalog now would add a database that nothing reads for six versions.

This record decides what the first searching phase contains, and how egress is controlled.

## Decision Drivers

- The phase should end with a command a person can run.
- Egress is refused, not warned about: only hosts named in the configuration are contacted.
- One HTTP client for the whole program, so there is one allowlist to defend.
- A port exists only with two real implementations.
- Tests never touch the network. Fixtures are synthetic, and reviewed by a person.
- A real search is run by a person, never by the coding assistant.

## Considered Options

1. **One phase, v0.3.0**, holding the HTTP client, the source port with PubMed and arXiv, and
   `lrcc search`. `work_id` and its catalog move to v0.9.0.
2. The roadmap as written: a client and `work_id` first, sources in the next version.

## Decision Outcome

Chosen option: **option 1**.

### Egress

- **The network is off unless the configuration turns it on**, with `network.enabled: true`.
- **`network.hosts` is the allowlist.** Each host carries its own `min_interval`, the seconds to
  leave between two requests to it. That is the per-source rate limit.

  ```yaml
  network:
    enabled: true
    hosts:
      eutils.ncbi.nlm.nih.gov: {min_interval: 0.4}
      export.arxiv.org: {min_interval: 3.0}
  ```

- **The client refuses, before any request:**
  - any request while the network is off;
  - any host that is not listed;
  - any scheme but `https`.
- **Redirects are not followed.** A redirect could lead to a host outside the list.
- **Retries:** transport errors, HTTP 429 and HTTP 5xx are retried with exponential backoff, four
  attempts in all. Any other status is an error at once.
- **Size ceiling:** a response above 50 MB is refused.
- **Only `adapters/http.py` may import an HTTP library.** A test fails if any other module does.

### Sources

- **The source port** is one method: a query and a limit in, a `SearchResult` out.
- **PubMed** uses E-utilities: `esearch` for the identifiers and the reported count, `efetch`
  for the records, in batches.
- **arXiv** uses its Atom API.
- **XML is parsed with `defusedxml`.** A document that declares entities is refused.
- **A `Record`** is frozen: source, the source's identifier, title, authors, year, DOI and
  abstract.

### The command

- **`lrcc search REVIEW_ID --source NAME`** runs the protocol's search string for that source.
  It prints the count the source reported, the count retrieved, and the records. It takes
  `--limit`, `--config` and `--json`.
- **It stores nothing.** Raw responses, runs and the database arrive in v0.5.0. Until then, a
  search is a preview of what a string returns.

### Dependencies

`httpx`, `tenacity` and `defusedxml`, with `respx` and `types-defusedxml` for the tests and mypy.

### Roadmap

- The v0.4.0 row is merged into v0.3.0.
- `work_id` and the work catalog move to v0.9.0, with deduplication.
- Secrets from `.env` move to v0.8.0, with Scopus, the first source that requires a key. PubMed's
  key is optional, and arXiv has none.

### Consequences

- Good, because the phase ends with a search a person can run and read.
- Good, because the allowlist and the rate limit live in one place, per host.
- Good, because no database is added before something reads it.
- Bad, because a phase that holds the egress boundary and two parsers is large to review.
- Bad, because a search that stores nothing cannot be replayed. It is a preview, and must not be
  reported as a run.
- Bad, because without PubMed's optional key, requests are limited to three per second.

### Confirmation

- Tests drive the client against a mocked transport and assert each refusal is made before any
  request is sent.
- A test scans `src/lrcc/` and fails if an HTTP library is imported outside `adapters/http.py`.
- A fixture makes every test fail if it opens a real connection.
- Source tests parse synthetic fixtures, including a document with entities, which is refused.
- CLI tests run `lrcc search` end to end against the mocked transport.

## Pros and Cons of the Options

### Option 1 - Client, sources and command together

- Good, because the client's rules are tested by the code that needs them.
- Bad, because the phase is bigger.

### Option 2 - The roadmap as written

- Good, because each phase is smaller.
- Bad, because the first of them ends with nothing to run, and builds a catalog nothing reads.

## More Information

- ADR-0006 (the `work_id` and catalog this record moves), ADR-0010 (configuration).
- The brief, sections 6 and 10.

## Implementation

**v0.3.0** built this record. Details settled while building it:

- **The client** is `src/lrcc/adapters/http.py`. It also refuses an explicit port other than 443.
  Its waits take an injected clock and sleep, so tests never really wait.
- **`tests/test_egress.py`** fails if any module but the client imports a networking library
  (`httpx`, `requests`, `socket`, `urllib.request`, `http.client` and others). `urllib.parse`
  only splits text and is allowed.
- **`tests/conftest.py`** makes every real connection attempt fail, for every test. A test
  asserts that it does.
- **Real PubMed answers carry a `DOCTYPE`.** `defusedxml` accepts a document type declaration
  and refuses entity declarations, which is the combination needed. The PubMed fixtures carry
  the `DOCTYPE`, so the tests cover it.
- **arXiv reports a rejected query with HTTP 200** and a feed holding one "Error" entry. The
  adapter recognises it and raises, instead of returning it as a record.
- **`--source` offers only sources that have an adapter.** A test keeps the command's choices
  equal to what composition can build. A protocol may still name `scopus` or `ieee`.
- **`--limit` defaults to 20** and is at most 10,000. The command prints both the reported count
  and the retrieved count, so a limit is never mistaken for the total.
- **Composition** is `src/lrcc/views/cli/composition.py`: the only view module that imports
  adapters, as ADR-0003 allows.
- **No real request was made while building this phase.** The real `lrcc search` command was run
  only for its two refusals: network off, and a host not listed. The first real search is the
  maintainer's.
