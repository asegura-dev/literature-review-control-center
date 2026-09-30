# LRCC - Literature Review Control Center

LRCC makes the identification and screening stages of a literature review reproducible and
auditable. Its purpose is that every number in a PRISMA 2020 flow diagram can be traced to a
stored response and a recorded decision. To get there, it:

- runs versioned searches across bibliographic databases and stores their responses;
- deduplicates records;
- records human screening with coded reasons;
- tracks which full texts were obtained;
- reports PRISMA 2020 counts;
- exports a versioned review bundle that is ready for data extraction.

## Status

**v0.1.0: a review can be created and its protocol checked. Nothing searches yet.** LRCC has
two commands:

- `lrcc init` creates a review in a workspace, with a protocol template to fill in;
- `lrcc validate` checks the protocol and prints the SHA-256 to register.

Searching arrives with the HTTP client and the first sources (v0.3.0 and v0.4.0). The route to
v1.0 is in [chapter 2, the roadmap](docs/02-roadmap.md).

## Try it

LRCC needs [uv](https://docs.astral.sh/uv/).

1. **Make an empty workspace folder.** It must be outside any git repository and outside
   OneDrive, because it will hold licensed PDFs. LRCC refuses it otherwise.
2. **Write a configuration file** that names the workspace, for example `C:\lrcc\config.yaml`:

   ```yaml
   workspace: C:\lrcc-workspace
   ```

3. **Run the two commands:**

   ```powershell
   uv sync
   uv run lrcc init my-review --config C:\lrcc\config.yaml
   uv run lrcc validate my-review --config C:\lrcc\config.yaml
   ```

   Set `LRCC_CONFIG` to that file's path to drop `--config`. Add `--json` to either command for
   machine-readable output.

   If the checkout lives in a synchronised folder on Windows, run `.\run.ps1` in place of `uv`.
   The [development guide](docs/guides/development.md) explains why.

`init` writes `reviews/my-review/protocol.yaml`, a synthetic example: replace it with your
review's question, criteria, search strings and extraction fields. `validate` names every problem
at once. When the protocol is valid, it prints the digest you register, on OSF for instance, so
that anyone can check the search used that exact file.

## What LRCC will not do

It will not download PDFs, scrape search engines, put a language model inside its pipeline, open
a listening port, or make any decision a person must make.

## Documentation

- [PRINCIPLES.md](PRINCIPLES.md): the non-negotiables.
- [VISION.md](VISION.md): why LRCC exists.
- [Chapter 0, project brief](docs/00-project-brief.md): the founding design.
- [Chapter 1, architecture](docs/01-architecture.md): how the code is laid out, and what
  enforces it.
- [Chapter 2, roadmap](docs/02-roadmap.md): where LRCC is and where it is heading.
- [Decision records](docs/adr/README.md).
- [Development guide](docs/guides/development.md): setting up, the quality gate, and how a phase
  is done.
- [CHANGELOG.md](CHANGELOG.md).

## Relationship with LACC

LRCC is a sibling of [LACC](https://github.com/asegura-dev/local-ai-control-center), the Local AI
Control Center. LRCC finds and screens; LACC verifies and writes. The review bundle is the only
contract between them (ADR-0001, ADR-0005).

## License

MIT (ADR-0009). See [LICENSE](LICENSE).
