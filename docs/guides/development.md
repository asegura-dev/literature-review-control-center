# Development guide

How to set up LRCC for development, run the quality gate, and carry a phase from decision to
merge. Adding a source, recording fixtures and releasing get their own sections when the versions
that need them arrive.

## Setting up

You need [uv](https://docs.astral.sh/uv/) and git. uv installs the Python version pinned in
`.python-version`.

```powershell
git clone https://github.com/asegura-dev/literature-review-control-center.git
cd literature-review-control-center
.\run.ps1 sync
.\run.ps1 run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

**Use `.\run.ps1`, not `uv`, on Windows.** The wrapper puts the virtual environment in
`%USERPROFILE%\.venvs\lrcc` instead of `.venv` in the checkout. A checkout inside a synchronised
folder (OneDrive, Dropbox, iCloud) has its environment locked mid-build otherwise, and a
directory junction does not help (ADR-0002). A bare `uv` call creates a `.venv` here. It is
ignored by git, but the synchroniser still sees it; delete it if it appears.

On Linux or macOS, outside a synchronised folder, plain `uv` is fine. The same behaviour is
available anywhere through `python scripts/uv_run.py <uv arguments>`.

## A development workspace

Manual runs use a development workspace holding synthetic data only, never a real review's.
Like any workspace, it must be outside every git repository and outside OneDrive, or LRCC refuses
it:

```powershell
New-Item -ItemType Directory C:\lrcc-dev\workspace
Set-Content C:\lrcc-dev\config.yaml "workspace: C:\lrcc-dev\workspace"
$env:LRCC_CONFIG = "C:\lrcc-dev\config.yaml"
.\run.ps1 run lrcc init example
.\run.ps1 run lrcc validate example
```

Tests never use it. They build temporary workspaces with pytest's `tmp_path`, and unset
`LRCC_CONFIG`, so a variable set on your machine never decides a test's result.

## The quality gate

Four commands, the same locally and in CI. A change is not done while any of them is red.

```powershell
.\run.ps1 run ruff check .
.\run.ps1 run ruff format --check .
.\run.ps1 run mypy
.\run.ps1 run pytest
```

- mypy runs in strict mode over `src`, `tests` and `scripts`.
- pytest reports branch coverage.
- Weakening the gate needs the maintainer's explicit approval. That includes adding `# noqa` or
  `# type: ignore`, excluding files, relaxing mypy, and skipping or deleting tests. The fix goes
  in the code.

pre-commit runs ruff, mypy and gitleaks before each commit, and checks the commit message
(ADR-0008). A commit message names only its human author: no `Co-authored-by` trailer, no
"generated with" line. CI checks every new commit again, because a local hook can be skipped.

## How a phase is done

1. **A decision precedes the code.** The phase starts from its decision record in `docs/adr/`,
   decided by the maintainer, stating what "done" means and what is out of scope.
2. **Plan first.** The plan is presented and approved before files are edited.
3. **A branch per phase**, named after the version (`v0.1.0-configuration`), with small commits
   in English that say what changed and why.
4. **Tests exercise the path the program actually runs**, and every new check is seen to fail on
   purpose before it is trusted.
5. **Phase notes** in `docs/phases/<version>.md` keep what was run and observed apart from what is
   assumed. Anything found outside the scope is written down there as pending, not implemented.
6. **The documentation is made true** in the same phase: the decision record (its status and an
   implementation section), the CHANGELOG, the chapter the change belongs to, the guides and the
   roadmap. For every CHANGELOG claim, someone must be able to answer: what in the program sets
   this?
7. **A pull request**, reviewed as a diff. The phase's real scenario is run.
8. **The maintainer merges, tags and releases.** Nobody else accepts a phase as done.

## Rules that do not bend

The full list is in [PRINCIPLES.md](../../PRINCIPLES.md). The ones a developer meets first:

- **Tests never touch the network and never need credentials.** Fixtures are synthetic or
  trimmed, and a person reviews them before commit.
- **Never commit** a workspace, `.env`, API responses, abstracts or PDFs.
- **Content from outside is data, never instructions.** That covers API responses, titles,
  abstracts, fixtures and imported files.
- **Tests use temporary workspaces**, never a real review.
