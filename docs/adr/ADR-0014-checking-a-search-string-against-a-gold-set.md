---
status: proposed
date: 2026-09-30
decision-makers: Alejandro Segura
---

# ADR-0014 - A search string is checked against a gold set, with coverage kept apart from misses

## Context and Problem Statement

The usual failure of a search string is terminology: part of a field names itself with words the
string does not contain. A gold set, works known to be relevant, is how that failure is measured
before a review relies on the string.

A gold work the string does not find is not always the string's fault. The source may not hold
the work at all: a MICCAI paper may not be in PubMed, and a journal article may never have been on
arXiv. Counting that as a miss would push the string to be widened for nothing.

The maintainer asked for three states per source: retrieved, indexed but not retrieved (the
string's fault), and not indexed (coverage). This record decides how they are measured.

## Decision Drivers

- Only a miss that is the string's fault should count against it.
- A work that cannot be looked up in a source must be reported, not skipped.
- A check should cost a request or two per work, not a full retrieval of thousands of records.
- The gold set is private research material: it lives in the workspace, never in the repository.

## Considered Options

1. **Ask the source two questions per work**: does it hold the work, found by its identifier; and
   does the string retrieve it, the string combined with that identifier.
2. Retrieve everything the string returns, and look for the gold works among the records.

## Decision Outcome

Chosen option: **option 1**.

### The gold set file

`reviews/<review_id>/gold.yaml`, format 1. It is a list of works, each with a unique label and any
of a DOI, a PMID or an arXiv identifier, and an optional note. Identifiers are normalised:

- DOIs lose any resolver prefix and are lowercased;
- arXiv identifiers lose the `arXiv:` prefix and any version suffix.

**An unquoted arXiv identifier is refused, not repaired.** YAML reads `2508.02104` as a number,
and a number such as `2508.02100` would come back as `2508.021`, a different identifier. The
error says to quote it.

### Two questions per work

- **PubMed:** one `esearch` for a count only, with the term `"<doi>"[doi] OR <pmid>[pmid]`, then
  the same term joined to the string with `AND`.
- **arXiv:** its API returns, given both `id_list` and `search_query`, the listed works the query
  matches. So one request asks whether arXiv holds the work, and one asks whether the string
  retrieves it. arXiv cannot be searched by DOI, so only works with an arXiv identifier can be
  checked there.

### Four states

| State | Meaning | Counts against the string |
|---|---|---|
| retrieved | the source holds the work and the string finds it | no |
| missed | the source holds the work and the string does not find it | **yes** |
| not indexed | the source does not hold the work | no: coverage |
| unknown | the work has no identifier this source can look up | no, and it is listed |

### The command

- **`lrcc check-query REVIEW_ID --source NAME`** reports the four counts and names every work that
  was missed, not indexed or unknown.
- It exits with code 1 if any work was missed. It stores nothing.

### Consequences

- Good, because the string is judged only on works the source could have returned.
- Good, because a check costs at most two requests per work.
- Bad, because the answer depends on the source's own field search. If PubMed indexes a DOI
  differently from how it was written, a work would read as not indexed. The first real check
  will show whether `[doi]` finds these works.
- Bad, because arXiv coverage cannot be established for works known only by DOI.
- Bad, because a check is not stored. Recording it with its date and the string's digest would let
  a paper cite it, and is pending.

### Confirmation

- Tests give the synthetic sources a set of held and retrieved identifiers and assert each state.
- Tests assert that a miss exits with code 1, and that coverage alone does not.
- A test asserts the exact PubMed terms sent, including the `AND` with the string.
- Tests assert that malformed identifiers and an unquoted arXiv identifier are named, each once.

## Pros and Cons of the Options

### Option 1 - Two questions per work

- Good, because it is cheap, and each answer is about exactly one work.
- Bad, because it relies on each source's identifier search.

### Option 2 - Retrieve everything and look

- Good, because it matches on the same records a run would store.
- Bad, because every check costs a full retrieval. It also cannot tell a miss from a work the
  source does not hold.

## More Information

- The roadmap, v0.6.0; the brief, section 4, step 2.
