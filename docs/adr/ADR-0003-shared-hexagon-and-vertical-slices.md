---
status: accepted (built in v0.0.1; amended by ADR-0010)
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0003 - A shared hexagon, a vertical slice per capability, and views that decide nothing

## Context and Problem Statement

LRCC will have about fourteen capabilities: init, check-query, search, import, replay, verify,
dedupe, screen, retrieve, scan, fulltext, report, export and status. They are driven first from
a CLI (Typer and Rich) and, after v1.0, from a window. Several of them share the same rules:
the `Record` and work models, the hash chain, the protocol, the HTTP client and the sources.

The structure has to answer two questions before the first module is written:

- where a capability's logic lives;
- how anyone can tell, mechanically, that it stayed there.

LACC offers a measured history. It started with flat modules (its ADR-001). Later it needed a
record to make ports and adapters visible in the layout (ADR-029). Its layering test checked
only that dependencies point inward, and logic leaked outward into the CLI unnoticed. Two
writers of one file format lived in the view and one reader in the core, and they drifted apart
with every test green (ADR-065). The converse rule, and a machine check for it, came afterwards
(ADR-066).

## Decision Drivers

- Shared rules must exist once: one HTTP client, one hash chain, one `Record`.
- A capability should be readable and testable in one place.
- A view (CLI now, a window later) must be replaceable without moving logic.
- The rule must be checked by a test, in both directions, from the first commit, while there is
  nothing to retrofit.
- No abstraction without two real cases.

## Considered Options

1. **A shared horizontal hexagon (`domain/`, `ports/`, `adapters/`) plus vertical slices under
   `features/`, with views under `views/`.**
2. Classic horizontal layers (`domain/`, `application/`, `infrastructure/`, `interface/`), with
   each capability's use case spread across them.
3. Pure vertical slices, each owning its own models and adapters.
4. Flat modules, split when they grow (LACC's starting point).

## Decision Outcome

Chosen option: **option 1**, because it keeps shared rules shared and puts each capability
in one place. Of the four, it is also the only one that can be checked mechanically in both
directions.

**The layout:**

```
src/lrcc/
├── domain/      entities, value objects and rules; pure
├── ports/       protocols, only where two real implementations exist
├── adapters/    sources/, storage/, notify/: the world
├── features/    one module or package per capability, holding its use case
└── views/       cli/ now, window/ after v1.0
```

**The dependency rules, inward:**

| Layer | May import |
|---|---|
| `domain` | the standard library and validation libraries (Pydantic); nothing else in `lrcc` |
| `ports` | `domain` |
| `adapters` | `domain`, `ports` |
| `features` | `domain`, `ports`; **not** `adapters`, and **not** another feature |
| `views` | `features`, and `adapters` only in composition code |

- A feature receives its adapters. It never constructs them.
- The view is the driving adapter, so building concrete adapters from the configuration
  (composition) is its job. That is the one place where a view touches `adapters`.
- Logic needed by two features moves down into `domain`. It is not imported sideways.

**The rule outward: a view decides nothing.** It is checked the way LACC's ADR-066 found
workable, because "logic" has no syntax but presentation does:

- A function in a view that never touches the presentation vocabulary (Rich `Console`, `Table`,
  `Panel`, `Progress`, prompts, Typer parameters), directly or through the functions it calls
  within the module (transitive closure), is not part of the view. The test names it.
- Exempt by name, not by assumption: the commands themselves, the entry point, and composition.

**`tests/test_layering.py` enforces both directions from v0.0.1.** It parses imports with the
standard `ast` module; it adds no dependency. On the empty package it must be seen to fail:
the phase is not done until a deliberately misplaced import and a deliberately logic-only view
function each make it fail by name.

**Refused:**

- **`import-linter`.** It covers only the inward rules, adds a dependency, and cannot express the
  outward one.
- **A storage port.** DuckDB in memory serves the tests; see ADR-0004.
- **A notification port** until a second notifier exists.

### Consequences

- Good, because a capability is found in one place: `features/<name>`.
- Good, because the window after v1.0 reuses every slice unchanged.
- Good, because the leak that cost LACC a corpus is checked from the first commit instead of
  being discovered.
- Bad, because the "no logic in views" test is a heuristic over a named vocabulary. A new
  presentation name must be added to the list, and a named-exception list is something that can
  be appended to instead of moving a function. That will be visible in review, not stopped by
  the test.
- Bad, because the rule that features do not import each other will sometimes force a small rule
  into `domain` earlier than it feels natural.
- Bad, because on an empty package the test proves only that it can fail, not that the code obeys
  it.

### Confirmation

- `tests/test_layering.py` exists, and runs in the gate on both operating systems.
- The phase notes record the two deliberate failures, with the test output, before they were
  reverted.

## Pros and Cons of the Options

### Option 1 - Shared hexagon plus slices

- Good, because shared rules exist once and capabilities are cohesive.
- Good, because both directions can be tested.
- Bad, because it has more folders than a small program needs on day one.

### Option 2 - Classic horizontal layers

- Good, because it is familiar and well documented.
- Bad, because a capability is spread across four folders, and reading "how does dedupe work"
  means opening all of them.
- Bad, because an `application/` layer tends to collect unrelated use cases in one place.

### Option 3 - Pure vertical slices

- Good, because each capability is fully self-contained.
- Bad, because it breaks "one HTTP client for the whole program": each slice would own its own
  client and allowlist, and an allowlist that exists several times is one that can be widened in
  one place.
- Bad, because shared models such as `Record` would be duplicated or imported sideways.

### Option 4 - Flat modules first

- Good, because it is the least structure on day one.
- Bad, because LACC measured the cost of retrofitting: two records (ADR-029, ADR-066) and a
  defect that reached a user's data (ADR-065).

## More Information

- LACC's records ADR-029, ADR-065 and ADR-066, in the `local-ai-control-center` repository.
- The exact presentation vocabulary is fixed when the first view is written, and is listed in the
  test, not here.

## Implementation

**v0.0.1** built `tests/test_layering.py`. Three details were fixed while writing it:

- **Composition is a module named `composition`** under `views/`. It is the only view module that
  may import `adapters`, and it is exempt from the outward check.
- **Views may not import `domain`**, as the table above says. If a view ever needs a domain type
  only to annotate what a feature returned, that is an amendment to this record, not a quiet
  widening of the test.
- **The closure runs through callees, not callers.** A view function is presentation if it
  touches the vocabulary directly or through a function it calls. Being called by a renderer does
  not count, or any logic reached from a renderer would be excused. A pure formatter must touch
  the vocabulary itself or be named in `EXEMPT_VIEW_FUNCTIONS`, where a reviewer sees it.

Both directions were seen to fail on the real package: a `domain` module importing `adapters`,
and a logic-only function in a view, each named by the test. The output is in
`docs/phases/v0.0.1.md`. Parametrized cases keep every inward rule and the outward rule proven
to fail on each run.

## Amendments

- **ADR-0010 (2026-09-29, v0.1.0). The domain may import PyYAML, besides Pydantic and its
  core.** Configuration and protocols are YAML. Parsing them is logic two slices share, and by
  this record's own rule shared logic moves down into the domain.
- **ADR-0010 (2026-09-29, v0.1.0). Views may import `domain`**, for the errors they catch and
  the types features return. The Implementation section above anticipated this amendment. The
  outward check still names any view function that does work without presenting it.
