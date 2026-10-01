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

**v0.8.0: a review can be created and its protocol checked. Its search strings can be run on
PubMed, arXiv, Scopus and IEEE Xplore as stored runs, or imported from a database's RIS
export, and those runs verified and replayed offline. PubMed and arXiv have been run against
the real services. Scopus has answered a real gold check, and IEEE Xplore a real preview and
gold check. The import has been tested against synthetic data only.** LRCC has eight
commands:

- `lrcc init` creates a review in a workspace, with a protocol template to fill in;
- `lrcc validate` checks the protocol and prints the SHA-256 to register;
- `lrcc search` runs the protocol's search string on one source and stores the run: every raw
  response with its digest, the records, and an entry in a hash-chained log. With `--preview`
  it stores nothing;
- `lrcc import` stores, as a run, the RIS files a database's web interface exported for the
  protocol's string, for a search the API cannot make;
- `lrcc status` lists a review's runs and checks that its log was not edited;
- `lrcc verify` checks every stored response and record against the log;
- `lrcc replay` rederives every run's records from its stored responses, without the network.
- `lrcc check-query` tests the protocol's search string against a gold set of works known to be
  relevant, telling a work the string misses from one the source does not hold.

Deduplication and screening come next.
The route to v1.0 is in [chapter 2, the roadmap](docs/02-roadmap.md).

## Try it

LRCC needs [uv](https://docs.astral.sh/uv/).

1. **Make an empty workspace folder.** It must be outside any git repository and outside
   OneDrive, because it will hold licensed PDFs. LRCC refuses it otherwise.
2. **Copy `config.example.yaml` to `config.yaml`** and set `workspace` to that folder. Git
   ignores `config.yaml`. To search, set `network.enabled` to `true`; LRCC contacts only the hosts
   listed there, and `min_interval` is the pause, in seconds, between two requests to one host.
3. **For Scopus or IEEE Xplore, copy `.env.example` to `.env`**, in the same folder as
   `config.yaml`, and fill in the keys you have. Git ignores `.env`, and LRCC reads keys from
   there only. PubMed and arXiv need no key.
4. **Run the commands:**

   ```powershell
   uv sync
   $env:LRCC_CONFIG = "config.yaml"
   uv run lrcc init my-review
   uv run lrcc validate my-review
   uv run lrcc check-query my-review --source pubmed
   uv run lrcc search my-review --source arxiv --preview
   uv run lrcc search my-review --source arxiv
   uv run lrcc import my-review scopus.ris --source scopus --searched 2026-09-30 --reported 480
   uv run lrcc status my-review
   uv run lrcc verify my-review
   uv run lrcc replay my-review
   ```

   `init` writes `reviews/my-review/protocol.yaml`, a synthetic example: replace it with your
   review's question, criteria, search strings and extraction fields. `validate` names every
   problem at once, and prints the digest you register, on OSF for instance. `check-query` tests
   a string against a `gold.yaml` of works you know are relevant. `search --preview` shows what a
   string returns and stores nothing; without `--preview` it stores a run. `import` stores a
   run from the RIS file a database exported when you ran the same string in its web interface,
   with the day of that search and the count it reported. `status` lists the runs, `verify`
   checks the stored files against the log, and `replay` rederives the records from those
   files, offline. Every command takes `--json`.

   If the checkout lives in a synchronised folder on Windows, run `.\run.ps1` in place of `uv`.
   The [development guide](docs/guides/development.md) explains why.

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
