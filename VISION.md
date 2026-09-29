# LRCC Vision

## The north

A literature review whose numbers anyone can check.

A systematic or scoping review makes a quiet promise: that its search found what there was to
find, and that its flow diagram counts what really happened. Most reviews cannot show it. The
searches were typed into web forms, the exports were merged in a spreadsheet, and the screening
was done in a tool that kept the decisions but not the reasons. The numbers in the diagram were
added up by hand at the end.

LRCC turns that promise into records:

- every search string is versioned and hashed;
- every response is stored as it arrived;
- every merge of two records into one work says why;
- every screening decision cites a coded criterion, names who made it, and is chained to the
  decisions before it;
- the PRISMA 2020 diagram is a query over those records, not a sum someone typed.

A reviewer who doubts a number can follow it back to its source. Anyone holding the stored
responses can replay the whole process and get the same counts. How a third party obtains those
responses, when providers' terms keep them out of the public record, is an open premise in the
roadmap.

## What it looks like when it arrives

- A protocol, with its eligibility criteria as codes, is fixed and hashed before the first
  search.
- A search string is tested against a gold set of works known to be relevant. What it misses is
  recorded, not hidden.
- Searches run against PubMed, arXiv, Scopus and IEEE Xplore, or are imported from their exports.
  A replay from the stored responses produces identical outputs. A re-run is recorded as a new
  run, because databases grow.
- A person screens, in a terminal, with coded reasons. A correction is a new entry, never an
  edit.
- Full texts are obtained by a person, through the access they have. LRCC tracks which arrived,
  and never downloads or opens them.
- At the end, a versioned review bundle carries everything the next step needs. That step is data
  extraction, in LACC or any other tool that reads the schema.

## What it is not

- It is not a search engine. It does not scrape.
- It is not a screening assistant that decides. After v1.0 a local model may suggest a decision,
  quoting the sentence that justifies it, and a person still decides every record.
- It is not a place for licensed content. The public repository holds code and method, never an
  abstract or a PDF.

## Why a separate tool

LRCC holds API keys and talks to external services; LACC holds private drafts and a model that
reads them. Keeping the two apart keeps the network surface away from the private material
(ADR-0001). A gap measured over an incomplete corpus is a false gap: LRCC supplies the complete,
documented corpus that LACC's measurements need.

## How it is built

- In small versions, each preceded by a decision record.
- Each version is closed by a green quality gate and documentation that says what the program
  actually does.
- It is measured against a real review before it is called v1.0.
