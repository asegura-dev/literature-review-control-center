---
status: proposed
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0015 - API keys from a `.env` beside the configuration, never recorded; Scopus and IEEE Xplore

## Context and Problem Statement

Scopus and IEEE Xplore need API keys, and PubMed accepts an optional one. The maintainer has
obtained keys and keeps them in a `.env` file. A key is a secret: it must never be printed,
logged, committed or stored in a review.

That last point is not automatic. A run stores the address of every request it made
(ADR-0012), so that the search can be audited. IEEE Xplore takes its key as a query parameter,
`apikey=...`. Recorded as it is sent, the key would land in the run log, in the review's
database and, later, in a bundle.

This record decides where keys come from, how they are kept out of everything LRCC stores, and
the first two sources that need them.

## Decision Drivers

- Secrets live only in `.env`, never in the configuration (the brief, section 10).
- A secret must never reach a terminal, a log, a run or a commit.
- The sibling LACC already decided where `.env` lives (its ADR-030), and the two should agree.
- Tests never touch the network, and never read a real `.env`.

## Considered Options

1. **`.env` beside the configuration file**, read only from there, as LACC does.
2. A path to the `.env` written in the configuration.
3. `.env` in the directory the command runs from.

## Decision Outcome

Chosen option: **option 1**.

### Where keys come from

- **Location.** LRCC reads `.env` from the directory that holds the configuration file, and from
  nowhere else. It does not search upward or try other places.
- **The real environment wins.** A variable already set in the environment is used instead of
  the file, so a deliberate export can override it without editing the file.
- **`.env` supplies keys only**: `SCOPUS_API_KEY`, `SCOPUS_INSTTOKEN`, `IEEE_API_KEY`,
  `NCBI_API_KEY`. Hosts and every other destination stay in the configuration, so no
  environment can widen what LRCC contacts.
- **The format is LACC's.** `NAME=value` lines, `#` comments, an optional `export`, and matching
  quotes stripped. A malformed line is skipped, not echoed. A key that is needed and missing is
  reported by its name and the file it should be in, never with a value.
- **No dependency.** LRCC has its own parser: the format is a few lines of code.

### Keys are never recorded

- **Headers.** A key sent in a header, as Scopus takes it, is not part of the recorded request.
- **Query parameters.** A key sent as a query parameter, as IEEE Xplore and PubMed take it, is
  recorded as `apikey=[redacted]`. The run shows that a key was used, never which.
- **An answer that repeats a key is refused.** Nothing from it is stored, because a stored
  response is kept byte for byte and could not be cleaned afterwards.
- **Error details are scrubbed.** When LRCC quotes the start of an error answer to explain a
  refusal, any key it sent is replaced by `[redacted]`.
- **Hidden in memory too.** The object holding the keys prints its variable names, never the
  values.

### IEEE Xplore

- The Metadata Search API, with `querytext` holding the protocol's string.
- Up to 200 records per call, paged with `start_record`.
- The daily limit is 200 calls. LRCC does not retry a refusal (HTTP 403), which is how the
  service answers an exhausted quota or an invalid key, so a retry would spend calls for nothing.
- **Gold checks** look a work up by its `doi` parameter, and ask whether the string retrieves
  it by sending the string and the DOI together.

### Scopus

- The Scopus Search API, with the protocol's string as `query`.
- The key, and the institutional token if there is one, are sent as headers.
- The `COMPLETE` view is requested, because screening needs abstracts. It pages with a cursor, 25
  records per call.
- Access also depends on the institution's subscription. A refusal quotes Elsevier's own
  explanation.
- **Gold checks** use `DOI("...")` and `PMID(...)` in the query, with the `STANDARD` view.

### PubMed

If `NCBI_API_KEY` is set, it is sent with every request and recorded as redacted. Without it,
nothing changes.

### Not in this record

Importing manual exports (RIS), and notification of long runs, stay in v0.8.0 for a later record.

### Consequences

- Good, because the keys reach the sources and nowhere else that LRCC writes.
- Good, because a missing key is named with the file that should hold it.
- Good, because LRCC and LACC find their secrets the same way.
- Bad, because the configuration must sit beside the `.env`. The maintainer's configuration
  moves next to the `.env` in the repository folder, where git ignores both.
- Bad, because two things rest on the services' documented behaviour and are not yet seen
  against them:
  - IEEE Xplore combining `querytext` with `doi`;
  - Scopus granting the `COMPLETE` view.

  The first real runs will show both.
- Bad, because the refusal of an answer that repeats a key could, in principle, refuse an answer
  that merely contains the same characters. Keys are long random strings, so this is not
  expected.

### Confirmation

- Tests store IEEE and Scopus runs with fake keys against the mocked transport. They then read
  every byte of the review's folder, database included, and assert the fake key is not there.
- A test gives an answer that repeats the key, and asserts that nothing was stored.
- Tests assert the parsing rules, that the environment wins, and that the printed form of the
  keys shows no value.
- A fixture removes the four variables from the environment of every test, so a key exported in
  a developer's shell never reaches a test.

## Pros and Cons of the Options

### Option 1 - Beside the configuration

- Good, because it is one place, the same as LACC, and never a guess.
- Bad, because it ties the two files' locations together.

### Option 2 - A path in the configuration

- Good, because the files can live apart.
- Bad, because it is a second setting to get right, and differs from LACC.

### Option 3 - The current directory

- Bad, because the result depends on where the command was run from, which is exactly the
  implicit behaviour LRCC refuses.

## More Information

- LACC's ADR-030, "Secrets come from a `.env` beside the configuration".
- ADR-0011 (the one HTTP client), ADR-0012 (what a run records).
