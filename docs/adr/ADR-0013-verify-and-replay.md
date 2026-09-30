---
status: accepted (built in v0.7.0)
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0013 - `verify` checks what is stored, and `replay` rederives it offline

## Context and Problem Statement

A run stores its raw responses, its records and a log entry holding their digests (ADR-0012).
Two promises of LRCC rest on that and were not yet kept by any command:

- that what is stored is what the log says;
- that a replay rederives everything from stored responses and produces identical outputs.

The first real run made the second promise concrete. PubMed reported 2,499 records and the run
retrieved 2,489. The ten missing were book records, `PubmedBookArticle`, which the adapter did
not read. The raw responses were stored, so the ten were on disk all along. Replaying them with
a corrected adapter shows the difference without asking PubMed again.

## Decision Drivers

- A replay never touches the network. Querying again is a re-run, which is a different run.
- A search and a replay must derive records with the same code, or "identical" means nothing.
- The log is append-only: a replay never rewrites a run.
- Names read from the log may have been edited, so they are never trusted as paths.

## Considered Options

1. **Two commands: `verify` compares what is stored with the log, and `replay` rederives the
   records and compares them with the log. Neither writes anything.**
2. One command that does both.
3. A replay that overwrites a run's records when the code derives something else.

## Decision Outcome

Chosen option: **option 1**.

### `lrcc verify REVIEW_ID`

It recomputes and compares, for every run:

- the hash chain of the log;
- the SHA-256 and size of each stored response;
- the digest of the records in the database.

It also reports what the log does not know about: a file inside a run folder that no entry
names, and a run folder that no entry names. It exits with code 1 on any mismatch.

### `lrcc replay REVIEW_ID`

- For every run, it reads the stored responses and derives the records again with the current
  code.
- If their digest is the one the run logged, the run is reproduced.
- If it is not, the replay reports both counts. It changes nothing: the run stays as logged, and
  the way forward is a re-run, which is a new entry.
- A response that is missing or does not match its digest stops that run's replay, and points at
  `verify`. Replaying altered answers would prove nothing.
- It exits with code 1 if any run is not reproduced.

### One derivation, shared

The source port gains `records_from(bodies)`: the raw answers of one search in, the records out,
with no request. `search` builds its records by calling it, and `replay` calls the same method.

### PubMed book records

The PubMed adapter reads `PubmedBookArticle` as well as `PubmedArticle`, in the order PubMed
gives them. A chapter uses its own title and authors; a record for a whole book uses the book's.

### Consequences

- Good, because a run can be checked and reproduced without the network and without trusting
  the database.
- Good, because a change in what the code derives is detected against real stored answers.
- Good, because a defect found after a run, as with the book records, is measured from disk.
- Bad, because a corrected adapter makes old runs replay as different. That is accurate, and it
  means a review built on those runs has to re-run them and say so.
- Bad, because `records_from` fixes each source's answer layout into the port: PubMed's first
  stored answer is the `esearch` one, by position.
- Bad, because neither command detects a log replaced whole together with its files and hashes.

### Confirmation

- Tests damage a stored run in each way, one at a time, and assert the damage is named:
  - an edited response;
  - a missing response;
  - an unlogged file;
  - an unlogged folder;
  - edited records;
  - a log that names a file outside the review.
- A test runs `replay` with the network off in the configuration and asserts that no request is
  made.
- A test replaces the adapter's derivation and asserts that `replay` reports the difference.
- A test asserts that `records_from` over a search's own answers returns that search's records.

## Pros and Cons of the Options

### Option 1 - Two commands that write nothing

- Good, because each answers one question, and neither can damage a review.
- Bad, because a person runs two commands to be sure.

### Option 2 - One command

- Good, because there is one thing to run.
- Bad, because "the files match the log" and "the code still derives the same records" fail for
  different reasons and call for different actions.

### Option 3 - A replay that overwrites

- Bad, because it edits a logged run, which the log exists to prevent.

## More Information

- ADR-0012 (runs and the log), ADR-0011 (the sources).
- The first real runs are recorded in `docs/phases/v0.5.0.md`.
