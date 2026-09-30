---
status: accepted (built in v0.0.1)
date: 2026-09-29
decision-makers: Alejandro Segura
---

# ADR-0002 - A uv-packaged application with a four-command quality gate

## Context and Problem Statement

v0.0.1 is the scaffold: the roadmap marks it done when "the gate is green on an empty package".
Before any code exists, the following must be fixed:

- how the package is built and installed;
- which Python it runs on;
- which commands make up the quality gate;
- what runs before a commit and in CI;
- where the virtual environment lives.

These choices are cheap now and expensive to change once code depends on them.

The sibling project LACC uses:

- `uv` with the `uv_build` backend and a `src` layout;
- `.python-version` pinned to 3.12 with `requires-python = ">=3.11"`;
- a gate of ruff, strict mypy and pytest.

LACC also recorded an operational lesson on the development machine. Its checkout sits inside a
synchronised folder (OneDrive), and a `.venv` inside it was locked mid-build: `uv sync` failed to
remove files with "Access is denied". A directory junction did not help, because the synchroniser
traverses reparse points. What worked was setting `UV_PROJECT_ENVIRONMENT` to a folder outside
the synchronised tree, through a small wrapper script (`run.ps1`).

## Decision Drivers

- The gate must be objective and identical locally and in CI.
- Tests must run against the installed package, not against files that happen to be importable
  from the working directory.
- The interpreter must be supported for the life of the thesis that motivates LRCC, and should
  match LACC's where nothing argues otherwise, so one machine runs both.
- No tooling that the task does not need yet.
- CI must cover Windows as well as Linux: the maintainer works on Windows, and path handling is
  central to the workspace boundary (ADR-0006).

## Considered Options

**Build and layout**

1. `uv` with the `uv_build` backend, `src/lrcc/` layout, `uv.lock` committed.
2. `uv` with the `hatchling` backend.
3. A flat package at the repository root.

**Python version**

1. Pin 3.12, `requires-python = ">=3.12"`.
2. Pin 3.11, `requires-python = ">=3.11"`, like LACC's floor.
3. Pin 3.13 or later.

**Coverage threshold**

1. Report coverage from v0.0.1; fix a threshold when the first real code lands (v0.1.0), as an
   amendment to this record.
2. Fix a threshold (for example 90%) from v0.0.1.
3. No threshold ever.

**Virtual environment on the development machine**

1. A wrapper script that sets `UV_PROJECT_ENVIRONMENT` outside any synchronised folder, as in
   LACC.
2. A `.venv` inside the checkout, excluded from synchronisation by hand.
3. A `.venv` junction to a folder outside.

## Decision Outcome

Chosen options:

- **Build and layout, option 1.** `uv init --package`, `uv_build` backend, `src/lrcc/`, lockfile
  committed, `.python-version` committed. A `src` layout forces tests to import the installed
  package.
- **Python, option 1: 3.12.** It is the interpreter LACC already runs on the same machine, it is
  supported until October 2028, and nothing planned needs a newer feature. The floor is 3.12,
  not 3.11: the project does not promise to support an interpreter it never tests.
- **The quality gate is exactly these four commands**, in this order, locally and in CI:

  ```
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy
  uv run pytest
  ```

  - `ruff` selects at least the pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify,
    pydocstyle (Google convention) and bandit (`S`) rule families.
  - `mypy` runs in `strict` mode over `src` and `tests`, configured in `pyproject.toml` so that
    the bare command is the whole check.
  - `pytest` runs with coverage reporting.
- **Coverage threshold, option 1.** On an empty package a percentage measures nothing. The
  threshold is fixed with the first real code and recorded here as an amendment. From then on,
  lowering it is weakening the gate.
- **pre-commit** runs ruff, mypy, gitleaks, and a `commit-msg` hook that rejects attribution
  trailers (ADR-0008).
- **CI** runs the gate on GitHub Actions on `ubuntu-latest` and `windows-latest`, with the
  pinned Python and `uv sync --locked`.
- **Virtual environment, option 1.** A `run.ps1` wrapper sets `UV_PROJECT_ENVIRONMENT` to
  `%USERPROFILE%\.venvs\lrcc` and clears an inherited `VIRTUAL_ENV`. On the development machine
  the gate is run through the wrapper (`.\run.ps1 run pytest`). CI calls `uv` directly.
- **Development dependencies named by this record:** `ruff`, `mypy`, `pytest`, `pytest-cov`,
  `pre-commit`. Accepting this record approves these names. Each is still added in the phase
  that needs it, and nothing else is added without a record or an explicit approval.
- **Refused for v0.0.1:** an API-reference generator (see More Information), `tox`/`nox`, a
  Makefile, and any runtime dependency. The empty package has none.

### Consequences

- Good, because tests exercise the installed artifact, and the gate is the same four commands
  everywhere.
- Good, because Windows path behaviour is tested on every push, not discovered on the maintainer's
  machine.
- Good, because the environment never sits inside a synchronised folder.
- Bad, because the local gate is run through a wrapper that CI does not use. Forgetting the
  wrapper silently creates a `.venv` inside the checkout; LACC recorded exactly that slip. The
  `.gitignore` excludes `.venv/` so the slip cannot reach a commit, but it can still reach the
  synchroniser.
- Bad, because a 3.12 floor excludes users on 3.11.
- Bad, because deferring the coverage threshold means v0.0.1 closes without one.

### Confirmation

- `pyproject.toml` carries `requires-python = ">=3.12"`, `[tool.mypy] strict = true`, the ruff
  rule selection and the pytest/coverage configuration.
- `.python-version` reads `3.12`.
- The CI workflow runs the four commands on both operating systems.
- `.pre-commit-config.yaml` lists ruff, mypy, gitleaks and the commit-msg hook.

## Pros and Cons of the Options

### Build and layout

- **`uv_build` + `src`:** Good, because it is uv's native backend and needs no configuration.
  Good, because it matches LACC. Bad, because it is younger than hatchling and has fewer
  extension points (none are needed).
- **`hatchling`:** Good, because it is mature and extensible. Bad, because it adds a build
  dependency with no feature LRCC uses.
- **Flat layout:** Good, because it is simpler to start. Bad, because tests can pass against
  files importable from the working directory while the installed package is broken.

### Python version

- **3.12:** Good, because it matches LACC on the same machine and has a long support window.
  Bad, because it forgoes features in newer releases.
- **3.11:** Good, because it widens the audience. Bad, because it is supported only until
  October 2027, and a floor that CI does not test is a claim nobody checks.
- **3.13 or later:** Good, because it has the longest support window. Bad, because it diverges
  from LACC and gains nothing the plan needs.

### Coverage threshold

- **Threshold with the first code:** Good, because the number is set when it can mean something.
  Bad, because the scaffold ships without it.
- **Threshold from day one:** Good, because it is simple to state. Bad, because a threshold set on
  an empty package is arbitrary.
- **Never:** Good, because it avoids gaming the number. Bad, because coverage can then fall with
  nothing to notice it.

### Virtual environment

- **`UV_PROJECT_ENVIRONMENT` wrapper:** Good, because nothing of the environment exists inside the
  checkout. Bad, because it is a habit to remember.
- **`.venv` excluded from sync by hand:** Good, because it needs no wrapper. Bad, because it
  depends on per-machine synchroniser settings that nothing in the repository can check.
- **Junction:** Bad, because LACC measured that the synchroniser traverses it and marks the
  environment's files read-only.

## More Information

- **The API reference is deferred.** The roadmap's v0.0.1 row listed an "API reference" in the
  documentation system. That needs a generator (for example `pdoc`, or MkDocs with
  `mkdocstrings`), and so a dependency and a decision. The generator is deferred to its own
  record before v0.14.0, when a public Python API exists (ADR-0005). The roadmap was amended on
  2026-09-29: the reference moved from the v0.0.1 row to the v0.14.0 row.
- Python support dates come from the CPython release schedule (PEP 693 for 3.12, PEP 664 for
  3.11) and should be rechecked when this record is accepted.

## Implementation

**v0.0.1** built this record. Three details were settled while building it, and are recorded here
because somebody will hit them later:

- **A second launcher, `scripts/uv_run.py`.** pre-commit hooks do not pass through `run.ps1`, and
  a bare `uv run` inside a hook would create a `.venv` in the checkout. The launcher does what
  `run.ps1` does, with the standard library only, so pre-commit runs it on any platform.
  `tests/test_environment.py` fails if the two name different environments.
- **Two per-file ignores in `pyproject.toml`, approved by the maintainer on 2026-09-29.** `S101` in `tests/**`
  (pytest reports through `assert`), and `S603` in `scripts/uv_run.py` (the launcher's only job is
  to start uv; the executable is resolved with `shutil.which`). No `# noqa` exists in the code.
- **Versions resolved on 2026-09-29:** uv 0.10.12 (pinned in CI), `uv_build>=0.10.12,<0.11.0`,
  ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0, pre-commit 4.6.2, gitleaks v8.30.1.
  pre-commit bootstraps the Go toolchain that the gitleaks hook needs; no Go installation is
  required.
- **Coverage** is reported, with no threshold, as decided. On the empty package it reads 100% of
  zero statements, which is exactly why no threshold was set yet.
