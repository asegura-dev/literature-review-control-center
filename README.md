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

**v0.0.1, Scaffold: nothing is usable yet.** The package is empty by design. This version
builds:

- the quality gate (ruff, strict mypy, pytest) and pre-commit hooks;
- CI on Linux and Windows;
- the tests that enforce the architecture;
- the founding decision records.

No command exists yet. The route to v1.0 is in [chapter 2, the roadmap](docs/02-roadmap.md).

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
