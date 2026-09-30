---
status: accepted
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0006 - A workspace outside any repository, one library folder per work, and an immutable `work_id`

## Context and Problem Statement

LRCC keeps two kinds of material that must never enter its public repository: each review's
state (protocol, database, raw responses) and a library of full-text PDFs that a person obtains
through institutional access. A work can belong to several topics and several reviews.

Three things need deciding:

1. **Where the workspace may live**, and what LRCC refuses.
2. **How it is laid out.**
3. **How a work is named on disk.** The name must be deterministic, safe on every filesystem, and
   never derived from a title.

The founding brief proposes a `work_id` such as `dou2020-3f9a2c`: first author, year, and a short
hash of the normalized DOI (or PMID, or arXiv ID). Reading it against the rest of the design
exposes four gaps:

- **A work may have no identifier at all.** Records from citation searching, conference papers
  or IEEE exports can arrive without a DOI, PMID or arXiv ID.
- **Author or year may be missing, or non-ASCII** (`Müller`, `Ødegaard`).
- **A six-hex-digit hash alone collides.** 24 bits give about 16.8 million values. Across 10,000
  works the expected number of colliding pairs is about 10,000² / (2 × 16.8 million), roughly 3.
  The author-year prefix is what makes collisions rare, not the hash.
- **The identifier can change.** When a preprint (arXiv ID) is merged with its published version
  (DOI), the brief keeps the published version. If `work_id` were recomputed from the preferred
  identifier, `library/<work_id>/` would have to be renamed. But `scan` never moves or renames
  anything.

There is also a placement risk. The maintainer's projects live inside a synchronised cloud
folder (OneDrive). A workspace placed there would copy licensed PDFs to a third party, against
the brief's rule that backups go only to hardware the user owns. It would also expose the DuckDB
files to mid-write locking (ADR-0004).

## Decision Drivers

- A workspace inside a git working tree is one `git add` away from publishing licensed content.
- Controls on exposure refuse rather than warn (the brief, section 10).
- Paths come from identifiers, never from titles.
- Nothing on disk is ever moved or renamed by the program.
- A work shared by two reviews is stored once.
- Replay must reproduce the same `work_id`s.

## Considered Options

**`work_id` scheme**

1. **`<author><year>-<hash>`, assigned once and never recomputed**, with explicit rules for
   missing parts, collisions and identifier changes.
2. `<author><year>-<hash>`, always recomputed from the currently preferred identifier (the
   brief's text read literally).
3. A pure hash of the identifier (for example 12 hex digits).
4. A random UUID, or a sequential number.

**Synchronised folders**

1. Refuse a workspace under a synchronised folder that can be detected; document the rule for
   the ones that cannot.
2. Warn only.
3. Document only.

## Decision Outcome

### Location

- **The workspace root must lie outside any git working tree.** LRCC walks up from the resolved
  root looking for `.git`, which may be a directory or a file (worktrees, submodules). If it
  finds one, it refuses.
- **Every path is resolved** (symlinks, `..`) and checked against the boundary before use.
- **Synchronised folders, option 1.** LRCC refuses a root under a synchronised folder it can
  detect from the environment, such as the `OneDrive`, `OneDriveCommercial` and
  `OneDriveConsumer` variables on Windows. It documents the rule for synchronisers it cannot
  detect.

### Layout

```
<workspace>/
├── library/
│   ├── catalog.duckdb          work identity: work_id and its aliases
│   └── <work_id>/
│       ├── fulltext.pdf
│       └── supplement-1.pdf ...
└── reviews/
    └── <review_id>/
        ├── protocol.yaml
        ├── review.duckdb
        └── runs/<run_id>/...
```

- **One folder per work, never per topic.** Topics are metadata.
- `review_id` is chosen by a person when the review is created. It is validated against
  `[a-z0-9-]` with a length limit, and refused otherwise. It is never derived from the review's
  title.

### `work_id`, option 1

- **Shape:** `<author><year>-<hash6>`, lowercase ASCII, `[a-z0-9-]` only.
- **`author`:** the first author's family name, NFKD-normalized, stripped to `[a-z]`, truncated
  to 20 characters. `anon` if there is none, or if nothing survives.
- **`year`:** four digits, or `nd` if there is none.
- **`hash6`:** the first six hex digits of the SHA-256 of a typed, normalized identifier. Type
  precedence is DOI, then PMID, then arXiv ID:
  - `doi:<lowercased DOI without resolver prefix>`
  - `pmid:<digits>`
  - `arxiv:<ID without version suffix>`
  - with no identifier: `title:<normalized title>|<year>`, and the work is flagged as having an
    unstable identity.
- **Assigned once, never recomputed.** Every identifier a work acquires later (the DOI of the
  published version, a PMID) is recorded as an alias. The folder name does not change.
- **Before assigning, look up.** LRCC checks every identifier of an incoming record against the
  aliases already known, so a work first seen through its preprint is found again through its
  DOI.
- **Collision:** if the computed `work_id` already names a different work, assignment stops with
  an error naming both works. It is never silently suffixed. Extending the hash is a decision for
  a person, recorded in the merge log.

### The work catalog

Works are shared across reviews, but each review has its own database (ADR-0004). Knowing that
an incoming record is a work already in the library therefore needs one workspace-level place.

- **Where.** `library/catalog.duckdb` holds two tables:
  - `works`: the `work_id` and when it was assigned;
  - `identifiers`: the typed, normalized identifier and the `work_id` it belongs to.
- **Uniqueness.** A `UNIQUE` constraint on the identifier makes "one identifier, one work" a
  property of the database, not of the code that writes to it.
- **Scope.** The catalog holds identity only. States, decisions and merges stay in each review's
  database.
- **Replay.** The catalog is rebuilt by replaying the reviews in the order their runs were
  recorded.
- **Considered and not recommended:** one `work.json` per library folder. It is readable and
  needs no database, but it cannot enforce identifier uniqueness atomically, and every lookup
  reads every folder.

### Consequences

- Good, because licensed content cannot be committed by accident: the program refuses to run
  where that is possible.
- Good, because folder names never change, so `scan` never needs to rename, and a PDF's path
  stays valid for the life of the review.
- Good, because a work shared by reviews is one folder.
- Good, because every edge case (no identifier, no author, a non-ASCII name, a collision, a
  preprint becoming published) has a rule instead of a surprise.
- Bad, because `work_id` is no longer a pure function of the work's best identifier. It is a pure
  function of the identifier the work was first seen with. Two workspaces that met the same
  work in different orders can name it differently. Replay is unaffected, because it processes
  stored responses in their recorded order, but the identifier is not portable across
  workspaces.
- Bad, because the workspace now has a second kind of database, the catalog, next to one
  database per review. Two reviews writing at once contend for the catalog's single writer. The
  catalog is also a single file whose loss breaks identity lookup until it is rebuilt by replay.
- Bad, because detecting synchronised folders is incomplete: Dropbox, iCloud and others without a
  reliable environment signal are covered only by documentation.
- Bad, because works without an identifier get a title-based hash. Two genuinely different works
  with the same normalized title and year, and the same first author and year prefix, would
  collide. The collision rule catches this, but a person must resolve it.

### Confirmation

- From v0.2.0: tests create a temporary git repository and assert that a workspace inside it is
  refused, including one where `.git` is a file.
- From v0.2.0: tests assert that a path escaping the boundary through `..` or a symlink is
  refused, and that a root under a simulated `OneDrive` variable is refused.
- From v0.3.0: table-driven tests cover `work_id` for a DOI, a PMID, an arXiv ID with a version
  suffix, a missing identifier, a missing author, a non-ASCII author, a missing year, and a
  forced collision.
- From v0.3.0: a test inserts the same identifier for two different works into the catalog, and
  asserts that the database refuses it.

## Pros and Cons of the Options

### `work_id` options

- **Assigned once, with aliases (1):** Good, because paths are stable and there are no renames.
  Bad, because it needs an alias index and is not portable across workspaces.
- **Recomputed (2):** Good, because it is a pure function of the work's best identifier. Bad,
  because a preprint becoming published forces a rename, which the design forbids.
- **Pure hash (3):** Good, because it has fewer parts and a longer hash. Bad, because it is
  unreadable to a person browsing the library, and it still has the rename problem if
  recomputed.
- **UUID or sequence (4):** Good, because it never collides and never changes. Bad, because it is
  not deterministic, so a replay from stored responses would produce different identifiers.

### Synchronised-folder options

- **Refuse detectable (1):** Good, because it is consistent with "refuse rather than warn". Bad,
  because the coverage is partial, and a user with a deliberate reason must choose another path.
- **Warn (2):** Good, because it is flexible. Bad, because a warning is the control the brief
  says exposure does not get.
- **Document (3):** Bad, because nothing checks it.

## More Information

- The brief, section 8, and the roadmap's premise that an ADR before v0.14.0 decides whether
  LACC points its workspace at the same root.
- Recommended for the maintainer's machine, not enforced by LRCC: a workspace under a local,
  unsynchronised path, backed up over the private network to hardware the user owns.
