---
status: proposed
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0009 - The MIT License, for code, documentation and schemas alike

## Context and Problem Statement

LRCC is a public repository meant to be cited, archived on Zenodo, and consumed by other tools
through its review bundle. It needs a license before its first public commit. The founding brief
proposes MIT "like LACC, to be confirmed by ADR"; LACC is indeed MIT-licensed.

The repository holds three kinds of material: source code, documentation (including a chapter on
the search method meant to double as supplementary material for papers), and the JSON Schema of
the bundle. It never holds third-party content: raw responses, abstracts and PDFs stay in the
workspace (ADR-0006).

## Decision Drivers

- Maximum reuse by researchers and by tools that consume the bundle, including closed ones.
- Consistency with LACC, so the two siblings can exchange code without a licensing question.
- One license is simpler to state, to cite and to comply with than several.
- Compatibility with the licenses of the dependencies LRCC will add.

## Considered Options

1. **MIT for everything in the repository.**
2. Apache-2.0 for everything.
3. GPL-3.0 (or AGPL-3.0) for the code.
4. MIT for the code, CC-BY-4.0 for the documentation.

## Decision Outcome

Recommended option: **option 1, MIT for everything**, with copyright held by the maintainer.

- `LICENSE` at the repository root carries the MIT text.
- `pyproject.toml` declares it.
- The Zenodo record of each release declares it.
- The license covers only what is in the repository. It grants no right over bibliographic
  records, abstracts or full texts, which the repository never contains and whose terms are set
  by their providers.
- The license of each dependency is checked when that dependency is proposed, and recorded in
  the approval.

### Consequences

- Good, because anyone may reuse the code, the schema and the method chapter with attribution,
  including in closed tools.
- Good, because code can move between LRCC and LACC freely.
- Good, because there is one license to cite.
- Bad, because MIT has no explicit patent grant, unlike Apache-2.0. For a research tool
  maintained by one person this risk is small, but it is real.
- Bad, because a license written for software is applied to prose. CC-BY-4.0 fits documentation
  better, and a reader reusing the method chapter in a paper may find MIT an unusual fit.
- Bad, because MIT allows closed derivatives. An improvement made by someone else need not come
  back.

### Confirmation

- `LICENSE` exists with the MIT text and the maintainer's name and year.
- `pyproject.toml` declares the license.
- From v0.15.0: the Zenodo metadata and `CITATION.cff` declare the same license.

## Pros and Cons of the Options

### Option 1 - MIT for everything

- Good, because it is short, widely understood, matches LACC, and is one license.
- Bad, because it has no patent clause and is awkward for prose.

### Option 2 - Apache-2.0

- Good, because it has an explicit patent grant and is permissive.
- Bad, because it is longer and needs NOTICE handling, and it differs from LACC.

### Option 3 - GPL-3.0 / AGPL-3.0

- Good, because derivatives stay open.
- Bad, because it deters integration into other tools, which is the purpose of a published bundle
  contract.
- Bad, because it differs from LACC, so code could not move between them freely.

### Option 4 - MIT code, CC-BY-4.0 docs

- Good, because each license fits its material.
- Bad, because there are two licenses to state and apply per file. The line between them blurs
  for docstrings, the generated API reference and the schema.

## More Information

- The brief, section 13, and LACC's `LICENSE`.
