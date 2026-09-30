# Changelog

All notable changes to LRCC are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0, a minor version may
break anything; every break is named here.

## [0.0.1] - Unreleased

The scaffold: an empty package, the gate that will judge everything added to it, and the decisions
that shape it.

### Added

- **Package.** An installable package, `literature-review-control-center`, importing as `lrcc`.
  It uses a `src` layout, the `uv_build` backend, Python 3.12, and a committed lockfile. It has
  no runtime dependencies (ADR-0002, ADR-0007).
- **Layers.** The empty layers `domain`, `ports`, `adapters`, `features` and `views`, each
  documented with what it may import (ADR-0003).
- **Quality gate**, configured in `pyproject.toml`: `ruff check`, `ruff format --check`, `mypy`
  in strict mode, and `pytest` with branch coverage reported but no threshold yet (ADR-0002).
- **`tests/test_layering.py`**, which checks the layout in both directions:
  - inward, every import respects its layer, and nothing imports LACC;
  - outward, no function in a view does work that touches no presentation.

  Each rule is proven able to fail on every run (ADR-0003, ADR-0001).
- **`tests/test_no_listening_port.py`.** The package contains no server-side networking
  (ADR-0005).
- **Commit-message check.** `scripts/check_commit_message.py` rejects co-author trailers,
  "generated with" lines and session trailers. It runs as a `commit-msg` hook and in CI over
  every new commit (ADR-0008).
- **pre-commit** with ruff, mypy, gitleaks and the commit-message hook.
- **`run.ps1` and `scripts/uv_run.py`**, which keep the virtual environment outside the checkout
  and outside synchronised folders. A test fails if the two disagree (ADR-0002).
- **CI.** GitHub Actions runs the gate on Ubuntu and Windows.
- **Documentation:**
  - `PRINCIPLES.md`, `VISION.md` and this changelog;
  - chapters 0 (brief), 1 (architecture) and 2 (roadmap);
  - the development guide;
  - decision records ADR-0001 to ADR-0009, with an index;
  - the phase notes of v0.0.1.
- **License.** The MIT license (ADR-0009).
