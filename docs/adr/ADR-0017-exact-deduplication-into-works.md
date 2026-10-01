---
status: proposed
date: 2026-10-01
decision-makers: Alejandro Segura
---

# ADR-0017 - Exact deduplication: records join works through shared identifiers

## Context and Problem Statement

The first review has stored runs on IEEE Xplore, PubMed and arXiv, and Scopus will follow. Many
records describe the same publication: an article indexed by two databases, or found again by a
re-run. Screening must judge each work once, and PRISMA reports how many duplicates were
removed.

ADR-0006 already decided how a work is named and where its identity lives:

- the `work_id` shape (`<author><year>-<hash6>`), assigned once and never recomputed;
- later identifiers kept as aliases;
- a collision refused, never suffixed;
- identity in `library/catalog.duckdb`, shared by every review of the workspace.

The brief sets the order of deduplication: normalized DOI first, then cross identifiers (PMID,
arXiv ID), then normalized titles with fuzzy matching, whose threshold is measured on real data
and whose merges a person confirms.

This record decides the exact part: how records are linked to works, and what LRCC does when
identifiers disagree. Fuzzy matching gets its own record once its threshold has been measured.

## Decision Drivers

- The same records, processed in the same order, must give the same works and `work_id`s.
- A `work_id`, once given, never changes (ADR-0006).
- Deduplication is incremental: a new run is joined to the works that already exist.
- Nothing is merged on a guess. An exact rule merges only on a shared identifier; anything else
  waits for a person.
- Every join records its reason.

## Considered Options

1. **Incremental linking through the catalog.** Records are taken in the order they were logged,
   and each one's typed identifiers are looked up. A record joins the work that holds any of
   them, or creates a work. A record whose identifiers point at two different works is refused.
2. Recomputing connected components over every record on each pass. Every pair of records that
   share an identifier is joined.
3. Matching on normalized titles from the start.

## Decision Outcome

Chosen option: **option 1**. It is the only one that keeps ADR-0006's promise that a `work_id`
never changes. With option 2, a new record that joins two components would rename one of them.
Option 3 is the fuzzy step, which needs a measured threshold and a person.

### A record's identifiers

Each record gives typed, normalized identifiers, in this order of precedence:

| Type | From | Normalization |
|---|---|---|
| `doi` | any record with a DOI | lowercase, resolver prefix removed |
| `pmid` | a PubMed record's own identifier | digits only, or not used |
| `arxiv` | an arXiv record's own identifier | without version suffix |
| `ieee`, `scopus` | the database's own identifier for the record | as given; `arxiv-record` for an imported arXiv record whose identifier is not an arXiv one |
| `title` | only a record with none of `doi`, `pmid`, `arxiv` | see below |

- **The database's own identifiers** (an IEEE Xplore article number, a Scopus EID) extend
  ADR-0006's list. They let a re-run find again a record that has no DOI.
- **A record without DOI, PMID or arXiv ID** also gets the identity ADR-0006 gives such a work:
  `title:<normalized title>|<year>`. The normalized title is NFKD-folded and lowercased, with
  every run of other characters replaced by one space. Its work is flagged as having an
  unstable identity. Only records that have no other identifier are joined this way; a record
  with a DOI is never joined on its title by this rule.

### Linking

- **All stored runs, in log order, record by record.** Only records not yet linked are taken,
  so a second pass links only what new runs added.
- **No known identifier:** a new work. Its `work_id` follows ADR-0006:
  - the first author's family name, the year;
  - the hash of the first identifier among `doi`, `pmid`, `arxiv`, `title`, or the database's
    own when nothing else exists.

  Every identifier of the record becomes an alias of the work.
- **Known identifiers, all of one work:** the record joins it. Its new identifiers become
  aliases, so a work first seen in IEEE Xplore is found again through the PMID of its PubMed
  record. The join records the identifier that matched.
- **Known identifiers of two different works: refused.** The command names the record and both
  works, and links nothing in that pass. Merging two works that already have `work_id`s is the
  same act as a person's fuzzy merge, so it is built with that step.
- **A computed `work_id` that already names another work: refused**, as ADR-0006 says.
- **The family name** comes from the first author:
  - `Family, Given` gives the part before the comma;
  - `Family GH`, with trailing initials, gives everything before the initials;
  - anything else gives the last word.

  Then ADR-0006's rule: NFKD, `[a-z]` only, 20 characters at most, `anon` if nothing is left.

### Where it is stored

- **The catalog** (`library/catalog.duckdb`, ADR-0006): `works` and `identifiers`, with a
  `UNIQUE` identifier. It is written before the review's links, so a failure between the two
  leaves identifiers that the next pass finds again, never a link to a work that does not exist.
- **The review's database:** one row per record, holding its run, its position, its work and
  the identifier that matched it (or `new`). That row is the merge log of the exact step.

### The command

`lrcc dedupe REVIEW_ID` links what is new and reports:

- how many records this pass linked;
- for each run, how many records first named a work, and how many joined one already seen;
- the identifier types that joined them;
- for the runs made under the current protocol, the records, the works among them, and the
  duplicates removed. Those are the numbers PRISMA asks for.

It refuses to run on a review whose run log does not verify, or whose records no longer match
their digests, because works built on edited records would prove nothing.

### Not in this record

- **Fuzzy matching on titles.** It needs:
  - candidate pairs, shown to a person;
  - the person's confirmations, recorded in a hash-chained log;
  - a threshold measured on the review's real records.
- **Merging two works**, whether found by a person or by a record that carries identifiers of
  both.
- **Rebuilding the catalog by replay**, and checking the links in `verify`.

### Consequences

- Good, because a duplicate found through a shared identifier is removed with no person
  needed, and the reason is kept.
- Good, because a re-run, or a review sharing works with another, finds the existing works
  instead of creating new ones.
- Good, because a conflict stops the pass instead of merging works on a guess.
- Bad, because a preprint and its published version without a shared identifier stay two works
  until the fuzzy step exists.
- Bad, because a conflict blocks deduplication until merging is built. The real data will show
  how often that happens.
- Bad, because the family-name rule is a heuristic. It does not change identity, only how the
  `work_id` reads, and it is applied to the first record seen, so a replay gives the same
  name.

### Confirmation

- Tests drawn from ADR-0006's own list cover the `work_id`: a DOI, a PMID, an arXiv ID with a
  version suffix, no identifier, no author, a non-ASCII author, no year, and a forced
  collision.
- A test inserts one identifier for two works into the catalog, and the database refuses it.
- Tests link records across sources through a DOI, and show the second source's identifiers
  becoming aliases. They also show a conflict refused with nothing written, and a second pass
  that links only new records.
- Command tests import synthetic exports, deduplicate them, and check the counts, the reasons
  and the summary for the current protocol.

## Pros and Cons of the Options

### Option 1 - Incremental, through the catalog

- Good, because `work_id`s never change, and a pass costs only its new records.
- Bad, because the result depends on the order records were logged, which is fixed by the log.

### Option 2 - Connected components each time

- Good, because the result does not depend on order.
- Bad, because a record that joins two components renames one of them, which ADR-0006 forbids.

### Option 3 - Titles first

- Bad, because a title match is a judgement, and the brief gives judgements to a person.

## More Information

- ADR-0006 (the `work_id` and the catalog), ADR-0012 (runs), ADR-0016 (imports).
- The brief, the section on works and states.

## Implementation

**v0.9.0** built this record while it was still proposed. Details settled while building it:

- **Where things are.**
  - Identifiers, names and linking: `src/lrcc/domain/works.py`, pure functions.
  - The catalog: `src/lrcc/ports/catalog.py`, a typing seam like the store port, and
    `src/lrcc/adapters/storage/duckdb_catalog.py`.
  - The links: a `links` table in each review's database, `src/lrcc/adapters/storage/duckdb_store.py`.
  - The command's use case: `src/lrcc/features/dedupe.py`.
- **The `links` table appears in a review's database** the next time any command opens it. It
  stays empty until a pass.
- **A pass that links nothing writes nothing.** A review without runs creates neither the
  catalog nor its own database.
- **Found while trying it in a scratch workspace.** A file imported under the arXiv source gave
  its records' own identifiers the `arxiv:` type, so a RIS digest counted as a stable arXiv
  identifier. Such identifiers now get `arxiv-record:`, and a test holds it.
- **Each rule was broken on purpose, and a test failed each time.** The rules were:
  - the refusal of a conflict and of a collision;
  - the title only without a stable identifier;
  - the family name before trailing initials;
  - new identifiers becoming aliases;
  - the guards on the log's chain and on the records' digests;
  - only unlinked records;
  - the current protocol's runs in the summary.
- **Not yet run on the real review.** That is the maintainer's step.
