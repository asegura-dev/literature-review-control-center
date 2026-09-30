---
status: accepted (built in v0.1.0)
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0010 - Configuration, protocol and workspace arrive together, with the first two commands

## Context and Problem Statement

The roadmap split the first real capability across two versions:

- v0.1.0: configuration and the review protocol, where a later amendment placed `init`;
- v0.2.0: the workspace boundary.

`init` writes a review into the workspace, so it cannot work before the boundary exists. That
amendment put it one version too early.

The roadmap's v0.1.0 also listed network settings, allowed hosts and secrets from `.env`. Nothing
reads any of them until the HTTP client (v0.3.0) and the first source that needs a key (v0.4.0).
A setting that nothing reads is a claim that nothing tests.

This record decides:

- what the first phase with a usable command contains;
- where the configuration lives;
- what a protocol file is and how it is hashed;
- which dependencies arrive.

## Decision Drivers

- The first phase should deliver something a person can run.
- ADR-0006 already fixes the workspace rules: outside any git working tree, not under a
  detectable synchronised folder, every path resolved and checked.
- Explicit over implicit: an empty required value is an error, never a silent default.
- No setting before the code that reads it.
- A registered protocol must be checkable by anyone with standard tools.

## Considered Options

1. **One phase, v0.1.0, holding configuration, protocol and workspace**, with `init` and
   `validate` as its commands. Network, hosts and secrets move to v0.3.0 and v0.4.0.
2. Keep v0.1.0 and v0.2.0 separate, and move `init` to v0.2.0.
3. Keep the roadmap as written: `init` in v0.1.0 writing wherever it is told, without the
   boundary.

## Decision Outcome

Chosen option: **option 1**.

### Commands

- **`lrcc init REVIEW_ID`**:
  - creates `library/` and `reviews/` in the workspace if they are missing;
  - creates `reviews/<review_id>/protocol.yaml` from a synthetic template;
  - refuses a review that already exists, and changes nothing.
- **`lrcc validate REVIEW_ID`**:
  - checks the protocol;
  - reports its contents and its SHA-256.
- Both take `--config PATH` and `--json`.

### Configuration

- A YAML file whose only field, for now, is `workspace`: required, non-empty and absolute.
- Unknown fields are errors, so a misspelt setting is caught rather than ignored.
- LRCC finds the file through `--config` or the `LRCC_CONFIG` environment variable. With
  neither, it stops and says so: there is no hidden default location.

### The protocol file, format 1

- **Fields, all required:**
  - `format`;
  - `review_id`, which must match its folder;
  - `title`;
  - a `question` with its framework and elements;
  - coded `criteria`;
  - one search string per source under `sources`;
  - the `extraction` fields.
- **Criteria:** codes look like `INC1` or `EXC1` and are unique. There is at least one of each
  kind.
- **Sources:** one of `pubmed`, `arxiv`, `scopus`, `ieee`, and at least one of them.
- **Hash:** the SHA-256 of the exact bytes of the file. Anyone can reproduce it with
  `sha256sum` or `Get-FileHash`. Editing the file, including a line ending, changes it; that is
  the point of registering it.
- **Parsing:** `yaml.safe_load`. The protocol is data, never code.

### Dependencies

`pydantic`, `pyyaml`, `typer` and `rich`, and `types-pyyaml` for mypy.

### Roadmap

- The v0.2.0 row is merged into v0.1.0.
- Network settings and allowed hosts move to v0.3.0, with the HTTP client that reads them.
- Secrets from `.env` move to v0.4.0, with the first source that needs a key.
- Later version numbers do not change.

### Consequences

- Good, because the first phase ends with a loop a person can use: init, edit, validate, and
  register the hash.
- Good, because every field that exists is read and tested.
- Bad, because a phase that combines two rows is larger to review, and it touches the workspace
  boundary, which the brief marks for line-by-line review.
- Bad, because hashing raw bytes makes the digest sensitive to invisible changes. An editor that
  rewrites line endings produces a new hash, and a person has to understand why.

### Confirmation

- CLI tests run both commands against temporary workspaces, including every refusal:
  - a workspace inside a repository;
  - one under a simulated OneDrive folder;
  - a path that escapes the boundary;
  - an existing review;
  - an empty required value.
- A test recomputes the reported hash with `hashlib` over the file's bytes.

## Pros and Cons of the Options

### Option 1 - One phase with two commands

- Good, because it delivers a usable command and fixes the misplaced `init`.
- Bad, because the phase is bigger.

### Option 2 - Two phases, `init` in the second

- Good, because each phase is smaller.
- Bad, because the first of them ends with nothing a person can run.

### Option 3 - `init` without the boundary

- Bad, because it would write files before ADR-0006 is enforced, which is exactly the exposure the
  boundary exists to prevent.

## More Information

- ADR-0006 (workspace, library layout, `review_id`).
- The brief, section 4, step 1 (the protocol and its registration).

## Implementation

**v0.1.0** built this record. Details settled while building it:

- **Two amendments to ADR-0003, forced by the first real code.** They are recorded there as well.
  - *The domain may import PyYAML.* Configuration and protocols are both parsed from YAML. Logic
    two slices share belongs in the domain, and the domain could not parse YAML. Only
    `yaml.safe_load` is used.
  - *Views may import the domain.* The CLI must catch `LrccError` and render the results
    features return. That the view decides nothing is still checked, by the outward rule of the
    layering test.
- **The coverage threshold ADR-0002 deferred is now 95%.** The suite reached 98.9%. A run of one
  test file was seen to fail the threshold at 41%.
- **Errors.** Every refusal is an `LrccError`: one sentence and optional detail lines.
  - The CLI prints them to stderr without a traceback, and exits with code 1.
  - With `--json` it prints `{"error": ..., "details": [...]}` to stdout.
  - Validation reports every problem in one pass, each located by field, for example
    `criteria.0.code: must look like INC1 or EXC1`.
- **A UTF-8 byte-order mark is accepted** in configuration and protocol files. Windows
  PowerShell 5.1 writes one by default, and the real-scenario run met it. The digest still
  covers the file's exact bytes, mark included.
- **Content is rendered as plain text, never as Rich markup.** A title containing `[bold]` is
  printed as written. A test fixes this.
- **The template** lives beside its slice, at `src/lrcc/features/init/protocol-template.yaml`.
  It is synthetic, and it is valid as written, which a test checks through `init` and then
  `validate`.
- **Links out of the workspace.** Tests create a junction on Windows and a symlink elsewhere,
  and both are refused. No test is skipped on either platform.
