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

**v0.5.0: a review can be created, its protocol checked, and its search strings run on PubMed
and arXiv as stored runs. It has been tested against synthetic answers only: no real search has
been run yet.** LRCC has four commands:

- `lrcc init` creates a review in a workspace, with a protocol template to fill in;
- `lrcc validate` checks the protocol and prints the SHA-256 to register;
- `lrcc search` runs the protocol's search string on one source and stores the run: every raw
  response with its digest, the records, and an entry in a hash-chained log. With `--preview`
  it stores nothing;
- `lrcc status` lists a review's runs and checks that its log was not edited.

Replay from the stored responses arrives in v0.7.0, and deduplication and screening after it.
The route to v1.0 is in [chapter 2, the roadmap](docs/02-roadmap.md).

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

4. **To search, turn the network on** in the configuration, and name the hosts LRCC may
   contact. It contacts no others:

   ```yaml
   workspace: C:\lrcc-workspace
   network:
     enabled: true
     hosts:
       eutils.ncbi.nlm.nih.gov: {min_interval: 0.4}
       export.arxiv.org: {min_interval: 3.0}
   ```

   ```powershell
   uv run lrcc search my-review --source arxiv --preview --config C:\lrcc\config.yaml
   uv run lrcc search my-review --source arxiv --config C:\lrcc\config.yaml
   uv run lrcc status my-review --config C:\lrcc\config.yaml
   ```

   The first line previews what the string returns and stores nothing. The second stores a
   run. The third lists the runs and verifies the log.

   `min_interval` is the pause, in seconds, between two requests to that host. The values
   above follow each service's published limits.

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
