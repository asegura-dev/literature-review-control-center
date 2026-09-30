---
status: accepted
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0001 - LRCC is a sibling of LACC, not LACC's `discover`

## Context and Problem Statement

LACC (Local AI Control Center, repository `local-ai-control-center`) is a local workbench for
private, auditable AI-assisted work over a researcher's own documents. Its roadmap already plans
a bounded `discover` capability for v3.0.0: a list of allowed domains in the configuration,
metadata only from sources such as PubMed, Crossref or arXiv, never a PDF download, and whatever
comes back treated as hostile text until it is accepted into the workspace.

The identification and screening stages of a systematic or scoping review need much more than
that: versioned search strings run against several bibliographic APIs with keys, stored raw
responses for replay, exact and fuzzy deduplication, append-only screening decisions with coded
reasons, full-text retrieval tracking, PRISMA 2020 counts and a versioned export.

The question is where that work lives: inside LACC, as an expanded `discover`, or in a separate
program.

## Decision Drivers

- **Exposure.** Review work needs API keys and many outbound requests. LACC holds private
  drafts, notes and the model that reads them. The less network surface sits next to that
  material, the less there is to go wrong.
- **A domain with its own rules.** Search provenance, deduplication, hash-chained decisions and
  flow-diagram accounting are a bounded context. They do not share vocabulary with verifying
  quotations or writing.
- **Citable releases.** A paper cites the exact release used for its search and screening. That
  release should change only when the search and screening code changes.
- **Reproducibility.** A replay of a review's search must not depend on the version of an
  unrelated writing tool.
- **Maintenance cost.** One person maintains both programs.

## Considered Options

1. A separate repository and program, LRCC, coupled to LACC only through a published contract
   (the review bundle).
2. Grow LACC's planned `discover` capability into the full review pipeline.
3. One repository holding two packages (a monorepo), released together or separately.

## Decision Outcome

Chosen option: **option 1, a separate program**, because it is the only option in which the
network surface, the release cycle and the domain rules of the review stay out of LACC without
extra machinery.

- LRCC finds and screens; LACC verifies and writes.
- The review bundle (ADR-0005) is the only coupling. LACC is its first consumer, not its owner:
  LACC imports a bundle as its acceptance step and treats everything in it as hostile until
  accepted.
- Re-scoping LACC's `discover` to importing LRCC bundles is a decision for LACC's own records,
  not this repository.
- **Refused:** a shared library extracted from LACC for the parts both programs need (a
  configuration loader, a workspace boundary, an HTTP client with an allowlist). Sharing it
  would bind the two release cycles together. Until the duplication is measured to cost more
  than the coupling would, LRCC writes its own versions.

### Consequences

- Good, because API keys, rate limits and bibliographic egress never enter LACC's process.
- Good, because an LRCC release can be cited, archived and replayed independently of LACC.
- Good, because the bundle has to be specified as a real contract, with a schema that a consumer
  can validate without importing LRCC.
- Bad, because some infrastructure is written twice: configuration, the workspace boundary and
  the HTTP client. The two copies can drift, and a fix in one is not a fix in the other.
- Bad, because a second repository means a second CI, a second changelog and a second set of
  guides to keep true.
- Neutral: the exposure argument is narrower than it first sounds. LRCC also holds a private
  library of licensed PDFs (ADR-0006). It never opens them, but they sit next to the keys. What
  this separation protects is LACC's material and its model from bibliographic egress, not every
  private file from all network access.

### Confirmation

- `pyproject.toml` declares no dependency on `local-ai-control-center`.
- The layering test (ADR-0003) fails if any module in `src/lrcc/` imports
  `local_ai_control_center`.
- The v0.14.0 criterion holds: a test consumer validates a bundle against its JSON Schema without
  importing `lrcc`.

## Pros and Cons of the Options

### Option 1 - Separate program, coupled by the bundle

- Good, because it keeps the keys and the egress away from LACC.
- Good, because each program keeps its own vocabulary and its own tests.
- Good, because releases are small and citable.
- Bad, because some infrastructure is duplicated.
- Bad, because a change to the contract has to be coordinated across two repositories.

### Option 2 - LRCC as LACC's `discover`

- Good, because there is one codebase, one configuration and one install.
- Good, because nothing is duplicated.
- Bad, because LACC's configuration would have to hold bibliographic API keys, which widens the
  exposure of the tool that holds private material.
- Bad, because a review's search provenance would be tied to LACC's release cycle, which moves
  for reasons unrelated to searching.
- Bad, because `discover` was scoped as metadata-only and bounded. Stretching it into
  deduplication, screening and PRISMA accounting turns a bounded capability into a second
  product inside the first.

### Option 3 - Monorepo with two packages

- Good, because shared code can be factored out once and reused.
- Good, because a change to the bundle and to its consumer can land in one commit.
- Bad, because the repository, its CI and its history become shared. That weakens the exposure
  boundary in practice: one checkout holds both.
- Bad, because it adds tooling (workspace packaging, per-package release tags) that neither
  program needs today.

## More Information

- Chapter 0, the project brief, sections 1, 2 and 5, records the founding argument.
- LACC's roadmap, v3.0.0, describes the `discover` capability as planned there.

## Implementation

- **v0.0.1.** `tests/test_layering.py` fails if any module under `src/lrcc/` imports
  `local_ai_control_center`; a parametrized case proves the rule can fail. `pyproject.toml`
  declares no runtime dependency at all. The bundle-side confirmation arrives with v0.14.0.
