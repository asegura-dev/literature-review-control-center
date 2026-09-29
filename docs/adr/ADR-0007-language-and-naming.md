---
status: proposed
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0007 - English for everything public, and one name defined and cited the same way everywhere

## Context and Problem Statement

LRCC's maintainer works in Spanish. The program, its documentation and the papers that use it
are read internationally. Two questions need a fixed answer before the first public file is
written:

- **Language:** which language is used for what.
- **Naming:** what the program is called in each place where it has a name (prose, the
  distribution, the import package, the CLI), and how a publication defines and cites it.

A publication cites a tool so that a reader can obtain the exact version that produced its
numbers. Zenodo, which will archive each release, issues both a concept DOI (all versions) and
a version DOI (one release).

## Decision Drivers

- Reviewers and replicators of a paper must be able to read the code, its messages and its
  history.
- A translation that lags behind its original is a false statement.
- A name must be unambiguous in prose and valid as a Python identifier.
- A citation must resolve to the exact release used.

## Considered Options

**Language**

1. **English for every public artifact**, commit messages included. Private notes in Spanish
   live outside the repository. There is no Spanish mirror.
2. English for code and documentation, Spanish for commit messages. The maintainer's other,
   private projects follow this convention.
3. Bilingual documentation (an English and a Spanish copy).

**Citation**

1. **Cite the version DOI** of the exact release used.
2. Cite the concept DOI.
3. Cite the repository URL and a version number.

## Decision Outcome

### Language, option 1

The following are written in English:

- code, identifiers, docstrings and comments;
- CLI messages;
- documentation, records and the CHANGELOG;
- commit messages and pull requests;
- the review bundle's schema.

Spanish belongs to the maintainer's private notes, which live outside the repository. The
repository contains no Spanish mirror of any document.

### Names

| Where | Name |
|---|---|
| Prose, first use | Literature Review Control Center (LRCC) |
| Prose, afterwards | LRCC |
| Repository and distribution | `literature-review-control-center` |
| Import package | `lrcc` |
| Command | `lrcc` |

### Citation, option 1

- **Definition in publications.** A publication defines LRCC at its first use, in the abstract
  and again in the body, as "the Literature Review Control Center (LRCC)".
- **Citation.** A publication cites the **version DOI** of the exact release it used, and
  reports that version number in its methods.
- `CITATION.cff` carries the concept DOI, so that "cite this software" in general resolves.
  Each release's metadata carries its version DOI.

### Consequences

- Good, because anyone who can read the paper can read the program and its history.
- Good, because there is never a second copy of a document to fall out of date.
- Good, because a citation resolves to the bytes that produced the numbers.
- Bad, because commit messages are written in the maintainer's second language. This departs
  from the convention of the maintainer's private projects, and costs some precision in the
  messages that explain *why*.
- Bad, because Spanish-speaking readers get no translation.
- Neutral: whether `lrcc` and `literature-review-control-center` are free on PyPI is not
  verified here. It matters only if LRCC is ever published there, which is not planned before
  v1.0.

### Confirmation

- A review of the diff of every phase: English-only public text is not mechanically checked, and
  this record does not pretend otherwise.
- `pyproject.toml` declares `name = "literature-review-control-center"` and the script `lrcc`.
- From v0.15.0: `CITATION.cff` exists with the concept DOI, and the README states how to cite a
  specific release.

## Pros and Cons of the Options

### Language options

- **English everywhere (1):** Good, because it gives one audience and one truth. Bad, because it
  is the maintainer's second language.
- **Spanish commits (2):** Good, because the maintainer writes the *why* in their first language.
  Bad, because the history, which is part of a reproducibility record, becomes unreadable to most
  replicators.
- **Bilingual docs (3):** Good, because it reaches more readers. Bad, because two copies will
  drift, and the lagging one is false.

### Citation options

- **Version DOI (1):** Good, because it is exact. Bad, because each paper must look up its own
  release's DOI.
- **Concept DOI (2):** Good, because it is one stable identifier. Bad, because it resolves to the
  latest version, not the one used.
- **URL and version (3):** Good, because it needs no archive. Bad, because a repository can move
  or vanish, and a URL is not a persistent identifier.

## More Information

- The brief, sections 1 and 15.
