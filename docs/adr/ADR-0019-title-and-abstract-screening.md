---
status: proposed
date: 2026-10-01
decision-makers: Alejandro Segura
---

# ADR-0019 - Title and abstract screening: a terminal session, a pilot, and a chained log

## Context and Problem Statement

The first review's searches give 851 works after deduplication. A person now screens each by its
title and abstract: include, exclude with a code, or uncertain. The brief sets the frame:

- screening is the only interactive step;
- an exclusion cites a protocol code;
- uncertain works go on to full text;
- a pilot calibrates the criteria, and a change after it is a versioned amendment, never a
  silent edit;
- every decision records who, when and why, and correcting one adds an entry.

The documents disagree on one point. The glossary in the maintainer's operating instructions
says every decision cites a code, while the brief codes only exclusions. And one thing in the code would break: `dedupe` counts the runs "made
under the current protocol", by the digest of the whole file. An amendment of the criteria
changes that digest, so after the pilot no run would count, and neither PRISMA nor screening
would have any records.

## Decision Drivers

- A person decides; LRCC never does (principle 4).
- Decisions are appended and hash-chained (principle 3).
- The order works are shown in should not bias the person, and must be reproducible to be
  reported.
- An amendment must be visible: which decisions were made under which criteria.

## Considered Options

The maintainer decided four choices on 2026-10-01, each among the options shown:

1. **The interface: a terminal session** (chosen), or a CSV round trip as for duplicates.
2. **Codes: only an exclusion cites one** (chosen), or an inclusion also cites the INC codes it
   meets.
3. **The order: random, from a reproducible seed** (chosen), or by year and title.
4. **The pilot: 50 works plus the frontier cases** (chosen), 85 works (10%), or no pilot.

## Decision Outcome

### What is screened

- **The unit is the group** of ADR-0018: one decision per publication, however many records
  name it.
- **The counted runs replace "runs under the current protocol".** For each source, the counted run
  is the latest run whose search string is the protocol's current string for that source. An
  amendment of the criteria leaves the strings, and so the counted runs, as they are. `dedupe`
  reports its PRISMA numbers over the counted runs. On the first review these are runs 4 to 6,
  as before.
- **Screened: every group with a record from a counted run.**

### The order

- **Each group's place is the SHA-256 of the review id and its `work_id`.** The order looks
  random, needs no stored state, and anyone can recompute it. A report states it in one
  sentence. A work added later, by a new run, takes its place in the same order.

### The pilot

- **The pilot is the first 50 groups of the order, plus the frontier cases.** The frontier cases
  are listed in `reviews/<review_id>/frontier.yaml`, in the gold set's format, and matched by their
  identifiers. A frontier case the searches did not find is named, not added.
- **`lrcc screen REVIEW_ID --pilot`** presents only those groups, and marks each decision as part
  of the pilot. **`lrcc screen-report REVIEW_ID`** gives the counts of the pilot and of the whole
  screening: included, excluded by code, uncertain, pending.
- **An amendment is the person's edit of the protocol**, then `validate`. Every decision records
  the digest of the protocol in force, and the first decision under a version keeps a copy of that
  protocol in `reviews/<review_id>/protocols/<sha256>.yaml`. The report counts decisions per
  version, so the criteria behind each one can always be read.

### Deciding

- **`lrcc screen REVIEW_ID`** opens the session. It shows the next undecided group: its title,
  authors, year, sources, DOI and abstract, with the longest abstract among its records. One key
  decides:
  - `i` include;
  - `e` exclude, then the code, from the protocol's exclusion codes;
  - `u` uncertain;
  - `n` a note for the next decision;
  - `s` leave it for later;
  - `q` stop.

  Each decision is written as it is made, so stopping, or a crash, loses nothing.
- **Without a terminal**, `lrcc screen REVIEW_ID --work WORK_ID --decision include|exclude|uncertain
  [--code EXC1] [--note TEXT]` records one decision, as every command must allow.
- **A decision names its group by any of its `work_id`s.** The group's decision is the latest
  among its works' decisions. Correcting one is a new entry.
- **The reviewer is the configuration's `reviewer`**, as for duplicates (ADR-0018).
- **The glossary should say that every exclusion cites a code**, as the brief does. It lives in
  the maintainer's operating instructions, outside this repository, so the maintainer corrects
  it.

### The record

- **One hash-chained log**, `screening`, in the review's database, built like the runs' and the
  decisions' logs. Each entry holds:
  - the `work_id`;
  - the decision, and the code for an exclusion;
  - the note;
  - whether it belongs to the pilot;
  - the protocol's digest;
  - the reviewer;
  - when.
- **`verify` checks its chain, and that every kept protocol matches its name.**

### Not in this record

- Full-text eligibility (v0.12.0), and retrieval (v0.11.0).
- A second, independent reviewer, and agreement between two.
- Suggestions from a model: never part of this deterministic pipeline (principle 9).

### Consequences

- Good, because 851 decisions can be made in sittings of any length, with nothing lost between
  them.
- Good, because the order is reproducible without storing anything, and is the same however many
  times the session is opened.
- Good, because after an amendment every decision still names the criteria it was made under.
- Bad, because a terminal shows plain text: no highlighting of terms in the abstract, as
  dedicated screening tools offer.
- Bad, because one reviewer screens alone, a limitation the report must declare.
- Bad, because the counted runs change `dedupe`'s report, merged in v0.9.0: "runs under the current
  protocol" becomes "counted runs". On the first review the numbers are the same.

### Confirmation

- Tests drive the session with keystrokes, and check the log, its chain and the stored protocol
  copy.
- Tests check the order against the SHA-256 rule, the pilot set with frontier cases, a code
  outside the protocol refused, a correction, and a decision named by a merged work.
- A test amends the protocol after a decision, and checks the counted runs and the report per
  version.
- `verify` names an edited screening entry and an edited protocol copy.

## Pros and Cons of the Options

- **Terminal session.** Good, because an abstract reads whole, one at a time. Bad, because it is
  plain text.
- **CSV round trip.** Good, because it is familiar from duplicates. Bad, because 851 abstracts in
  spreadsheet cells are hard to read.
- **Codes for exclusions only.** Good, because an inclusion means every INC criterion holds. Bad,
  because an inclusion carries no reason beyond its note.
- **Random order from a hash.** Good, because it is reproducible and stores nothing. Bad, because
  the person cannot follow a theme.
- **A pilot of 50 plus the frontier cases.** Good, because the hardest cases calibrate the criteria
  early. Bad, because 50 works may not show every way a criterion is misread.

## More Information

- The brief: the steps of a review (screening) and the states of a work.
- ADR-0012 (runs and their chain), ADR-0014 (the gold set's format), ADR-0018 (groups and the
  reviewer).

## Implementation

**v0.10.0** built this record while it was still proposed. Details settled while building it:

- **Where things are.**
  - Decisions, order, pilot and the chain: `src/lrcc/domain/screening.py`.
  - The session and the report: `src/lrcc/features/screen.py`.
  - The `screening` table and the kept protocols: `src/lrcc/adapters/storage/duckdb_store.py`.
- **One picture of a review, for two features.** Screening needs the same works and groups as
  deduplication, and a feature may not import another. Assembling them, and refusing a review
  whose logs or records were edited, moved into `src/lrcc/domain/review_works.py`. Both
  features use it.
- **One chain check for three logs.** Runs, duplicate decisions and screening are all checked by
  `link_problems` in `src/lrcc/domain/runs.py`.
- **The counted runs** are `counted_runs` in the same module. `dedupe`'s report now says
  "counted runs", and its JSON `counted_runs`. On the first review, runs 4 to 6 are counted, as
  before.
- **A session opens only with a reviewer**, even to look, because every key may record.
  Stopping with Ctrl+C keeps what was decided, since each decision is written as it is made.
- **On the first review's real records**, in a scratch workspace, the report needed 0.7 seconds:
  - the pilot holds 53 groups, the first 50 and 3 frontier cases found beyond them;
  - all five frontier cases were found by the searches;
  - a session opened on the pilot showed the protocol's seven exclusion codes and a work with
    its abstract. It was left without a decision.
- **Each rule was broken on purpose, and a test failed each time.** There were thirteen:
  - the code an exclusion needs, and only an exclusion;
  - the order's key;
  - the frontier joining the pilot;
  - the latest decision in force, and a member's decision speaking for its group;
  - the latest run counted, and only with the current string;
  - the protocol kept;
  - only screened works;
  - the pilot marked;
  - the screening chain checked;
  - the reviewer required.
- **No screening decision has been recorded on real records.** That is the maintainer's work.
