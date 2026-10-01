---
status: proposed
date: 2026-10-01
decision-makers: Alejandro Segura
---

# ADR-0018 - Fuzzy duplicates: candidate pairs by title, confirmed by a person in a CSV file

## Context and Problem Statement

Exact deduplication (ADR-0017) joins records that share an identifier. On the first review's real
records it removed 82 duplicates, and it left about 35 apart: arXiv preprints, which carry no
DOI, beside their published versions. Most of those have identical normalized titles.

The brief says fuzzy merges are confirmed by a person, with a threshold measured on real data.
The measurement exists (the v0.9.0 phase notes). Every pair of works from different sources was
scored on normalized titles:

- 34 pairs at 0.95 or more, nearly all preprints beside their published versions;
- 2 between 0.80 and 0.95;
- 7 between 0.75 and 0.80;
- hundreds below.

The same band also holds two different papers by one group, and a conference paper beside its
journal extension. A score cannot decide; it can only propose.

## Decision Drivers

- A person decides, and is recorded with the decision (principle 4).
- Decisions are appended and hash-chained; a correction is a new entry (principle 3).
- Every command runs without prompts; screening is the only interactive step.
- The person has dozens of pairs to judge, with the titles side by side.
- The review's counts must reflect the confirmed merges.

## Considered Options

1. **A CSV round trip.** LRCC writes the pending pairs, the person fills in a decision per row in
   a spreadsheet, and LRCC reads the file back.
2. One command per pair, `lrcc same` and `lrcc different`.
3. An interactive prompt, pair by pair.

## Decision Outcome

Chosen option: **option 1**, decided by the maintainer on 2026-10-01, with the threshold and the
reviewer's name below. A spreadsheet shows titles, authors and years side by side, and a
person can judge dozens of pairs in one sitting. Option 3 would make deduplication interactive,
which only screening may be.

### Candidate pairs

- **Two works of the review are a candidate pair** when the best similarity between their
  records' normalized titles is 0.80 or more. The score is the ratio of Python's
  `difflib.SequenceMatcher`. Pairs already decided, and works already in one group, are left
  out.
- **0.80 is the default, from the measurement above.** It keeps the preprint whose title changed
  on publication (0.82), and lets through a few pairs that the person rejects. `--min` changes
  it for one listing.
- **The list is deterministic**: by score, highest first, then by `work_id`.

### The commands

- **`lrcc candidates REVIEW_ID [--min 0.80] [--csv FILE]`** prints the pending pairs, and with
  `--csv` writes them to a new file. An existing file is never overwritten. Each row holds:
  - both `work_id`s and the score;
  - an empty `decision` and an empty `note`;
  - each work's title, first author, year, sources and DOI.

  Cells that begin like a formula (`=`, `+`, `-`, `@`) are escaped with a leading `'`.
- **`lrcc decide REVIEW_ID FILE`** reads the file back:
  - a row whose `decision` is `same` or `different` is recorded;
  - an empty decision stays pending;
  - any other value refuses the whole file, naming the row;
  - so does a `work_id` that is not a work of the review.

  The file may be UTF-8, with or without a byte-order mark, or Windows-1252, as a spreadsheet
  saves it. It may be separated by commas or semicolons. LRCC reads only the `work_id`s, the
  decision and the note; it recomputes the score itself rather than trust the file's.

### The record of a decision

- **Each decision is one entry in a hash-chained log** in the review's database:
  - the two `work_id`s, `same` or `different`;
  - the score LRCC computed, the note;
  - the reviewer;
  - when, in UTC.

  The chain is the one runs use: canonical JSON, each hash covering the entry and the hash
  before it.
- **The reviewer is `reviewer` in the configuration.** `decide` refuses to run without it. This
  amends ADR-0010, which listed the configuration's fields.
- **A later decision on the same pair replaces the earlier one**, as a new entry. A decision equal
  to the pair's current one is not recorded again, so reading the same file twice adds nothing.
- **A contradiction refuses the whole file.** That is the case when `different` would separate
  two works that `same` decisions join, directly or through other works.

### Groups

- **Works joined by `same` decisions form one group.** The group is the unit a review counts and,
  from v0.10.0, screens.
- **The published version is kept over the preprint**, as the brief says. The group is named by
  its work with a DOI-based identity, then PMID, then arXiv, then the first named.
- **Groups live in the review**, as ADR-0006 keeps merges in each review's database. The catalog is
  unchanged: both works keep their `work_id`, and another review decides for itself.
- **`dedupe` counts groups.** For the current protocol's runs it reports the works, the
  duplicates removed by identifiers and by a person, and how many decisions are recorded. It
  does not compute the pending pairs: comparing every pair of titles is the slow step, and only
  `candidates` pays for it.
- **`verify` checks the decisions' chain** as it checks the runs'.

### Not in this record

- Merging works across reviews, in the catalog.
- A record whose identifiers name two works: it still stops the exact step (ADR-0017).
- Comparing anything but titles: authors, years and abstracts are shown to the person, not
  scored.

### Consequences

- Good, because no title match becomes a merge without a person, and every merge names who
  decided and when.
- Good, because the person judges in a spreadsheet, and a half-filled file can be read now and
  finished later.
- Good, because a mistaken decision is corrected by a new one, and the log keeps both.
- Bad, because comparing every pair of works grows with the square of their number. At 886 works
  it takes about 15 seconds; a review with tens of thousands would need blocking.
- Bad, because a spreadsheet can damage a file, by changing its encoding or separators or by
  reading cells as numbers. LRCC reads only the identifiers and the decision, and refuses what
  it cannot read.
- Bad, because `reviewer` names one person. Two reviewers deciding independently are not
  supported yet.

### Confirmation

- Tests score pairs, order them, and leave out decided pairs and grouped works.
- Tests write a CSV, fill it as a spreadsheet would (UTF-8 with a mark, Windows-1252,
  semicolons), read it back, and check the log, its chain and the counts.
- Tests refuse an unknown decision, an unknown work, a contradiction, a missing reviewer and an
  existing output file, with nothing recorded.
- A test escapes a title that begins like a formula.
- A test edits a decision in the database, and `verify` reports it.

## Pros and Cons of the Options

### Option 1 - CSV round trip

- Good, because the person sees everything side by side, and can stop half-way.
- Bad, because spreadsheets alter files, so reading back must be strict.

### Option 2 - One command per pair

- Good, because it is the simplest to build and to audit.
- Bad, because about 35 commands, each with two `work_id`s typed by hand, invite mistakes.

### Option 3 - Interactive prompt

- Bad, because deduplication would become an interactive step, which the project reserves for
  screening.

## More Information

- ADR-0006 (merges stay in each review), ADR-0010 (the configuration), ADR-0017 (the exact
  step), and the v0.9.0 phase notes (the measurement).

## Implementation

**v0.9.0** built this record while it was still proposed. Details settled while building it:

- **Where things are.**
  - Scoring, decisions, the chain and groups: `src/lrcc/domain/fuzzy.py`.
  - The CSV round trip: `src/lrcc/domain/pairs_csv.py`.
  - The decisions' log: a `decisions` table in each review's database.
  - The three commands: one slice, `src/lrcc/features/dedupe.py`. They share the loading and
    the checks of the review.
- **Every log is written in one canonical form.** The JSON form runs used became the public
  `canonical` in `src/lrcc/domain/runs.py`, so both logs hash the same way.
- **The listing is fast where it can be exact.** Each pair of titles passes two cheap upper
  bounds before the full ratio:
  - the lengths, as `real_quick_ratio` would compute them;
  - the shared characters, from counts made once per title. Over the alphabet of normalized
    titles this bound is exactly `quick_ratio`.

  A test checks the listing against scoring every pair, at three thresholds. On the first
  review's 886 works the listing still takes about 15 seconds: about 75,000 pairs pass both
  bounds, and the full ratio costs 147 microseconds each.
- **`dedupe` stopped computing the pending pairs.** It took 20 seconds that way; it now takes
  under one.
- **A score is the one its pair was listed with.** `difflib`'s ratio is not quite symmetric. Both
  the listing and a decision therefore score the earlier work's titles against the later
  work's, in the order the works first appear.
- **On the first review's real records**, in a scratch workspace: 37 pairs at 0.80 or more. Of
  those, 33 score 1.0 and the other 4 lie between 0.81 and 0.95, as the measurement foresaw.
- **`autojunk` is off.** From 200 characters on, `difflib` drops a text's most frequent
  characters, and a long title nearly equal to another scored 0.2 instead of 0.973. Found while
  comparing abstracts for the maintainer; a test holds it. On the review the listing did not
  change.
- **Each rule was broken on purpose, and a test failed each time.** The rules were:
  - the contradiction refusal;
  - decided pairs and grouped works left out;
  - the published version kept;
  - the reviewer required;
  - an unchanged decision not recorded again;
  - formula escaping;
  - the latest decision in force;
  - `verify` checking the chain;
  - never overwriting the file;
  - a pair twice in one file;
  - the person's duplicates counted;
  - both cheap bounds.
- **No decision has been recorded on the real review.** That is the maintainer's to make.
