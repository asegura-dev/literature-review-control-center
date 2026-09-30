# Changelog

All notable changes to LRCC are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before 1.0.0, a minor version may
break anything; every break is named here.

## [0.3.0] - Unreleased

The first search: a protocol's string run against PubMed or arXiv, through a client that contacts
only the hosts the configuration names.

### Added

- **`lrcc search REVIEW_ID --source pubmed|arxiv`.** It runs the protocol's search string for
  that source and prints the count the source reported, the count retrieved and the records. It
  takes `--limit`, `--config` and `--json`. It is a preview: nothing is stored yet (ADR-0011).
- **Network settings in the configuration.**
  - The network is off unless `network.enabled` is `true`.
  - `network.hosts` is the allowlist. Each host carries `min_interval`, the seconds to leave
    between two requests to it.
- **One HTTP client.** It refuses, before anything is sent:
  - any request while the network is off;
  - a host that is not listed;
  - anything but HTTPS on the default port.

  It never follows a redirect. It retries transport errors, HTTP 429 and HTTP 5xx with backoff,
  four attempts in all, and refuses a response above 50 MB.
- **The source port**, with PubMed (E-utilities) and arXiv (Atom API) as its two
  implementations. XML is parsed with `defusedxml`; a document that declares entities is
  refused.
- **A frozen `Record`:** source, the source's identifier, title, authors, year, DOI and abstract.
- **Two gate checks:**
  - no module but the HTTP client may import a networking library;
  - every test fails if it opens a real connection.
- **Runtime dependencies:** httpx, tenacity, defusedxml (ADR-0011).

### Changed

- **Roadmap:**
  - v0.4.0 is merged into v0.3.0;
  - `work_id` and its catalog move to v0.9.0, with deduplication;
  - secrets move to v0.8.0, with the first source that requires a key.

## [0.1.0] - Unreleased

The first commands: create a review and check its protocol, inside a workspace that refuses to
expose what it holds.

### Added

- **`lrcc init REVIEW_ID`.** Creates `library/` and `reviews/<review_id>/protocol.yaml` in the
  workspace, from a synthetic template, and prints the protocol's SHA-256. It never overwrites
  an existing review. The template is pinned to LF line endings, so `init` writes the same bytes,
  and prints the same digest, on every platform (ADR-0010).
- **`lrcc validate REVIEW_ID`.**
  - It checks every field of the protocol and reports every problem in one pass, each located
    by field.
  - When the protocol is valid, it prints its criteria, sources, extraction fields and the
    SHA-256 of the file's exact bytes: the digest to register.
- **`--json` on both commands**, for results and errors alike (ADR-0005).
- **Configuration.**
  - It is a YAML file with one required field, `workspace`, which must be a non-empty absolute
    path.
  - It is named by `--config` or `LRCC_CONFIG`. There is no default location.
  - Unknown fields are errors.
- **Protocol format 1.**
  - Its sections are the question with its framework, coded INC/EXC criteria, one search
    string per known source (`pubmed`, `arxiv`, `scopus`, `ieee`) and extraction fields.
  - Every field is required.
  - It is parsed with `yaml.safe_load`, so a protocol cannot run code.
- **The workspace boundary (ADR-0006).** LRCC refuses a workspace that:
  - does not exist;
  - is inside a git working tree;
  - is under a folder named by the `OneDrive`, `OneDriveCommercial` or `OneDriveConsumer`
    variables.

  Every path is resolved before it is checked, so `..`, symlinks and junctions cannot lead
  outside.
- **Runtime dependencies:** pydantic, pyyaml, typer, rich (ADR-0010).

### Changed

- **Coverage threshold.** The gate now fails below 95% coverage, as ADR-0002 deferred to the
  first real code.
- **ADR-0003 amended by ADR-0010:**
  - the domain may parse YAML;
  - views may import domain types and errors.

  The check that views decide nothing is unchanged.
- **Roadmap:**
  - v0.2.0 is merged into v0.1.0;
  - network settings and allowed hosts move to v0.3.0;
  - secrets move to v0.4.0.

## [0.0.1] - 2026-09-29

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

[0.0.1]: https://github.com/asegura-dev/literature-review-control-center/releases/tag/v0.0.1
