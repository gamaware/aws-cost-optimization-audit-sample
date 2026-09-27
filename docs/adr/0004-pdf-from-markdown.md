# ADR 0004: Build the PDF from the Markdown with the shared pandoc LaTeX image

## Status

Accepted

## Context

Clients expect a PDF; reviewers want a diffable source. Two hand-maintained documents drift apart. The shared
`report` workflow in `gamaware/.github` already renders every sample report in CI with a pinned `pandoc/latex`
container. A second PDF engine in this repository would publish a PDF that differs from the one CI proves.

## Decision

`report/REPORT.md` is canonical. `scripts/build_pdf.py` renders it by running the same pinned `pandoc/latex`
image as the shared `report` workflow, with the arguments `ci.yml` passes to that workflow: xelatex, landscape A4,
1.8 cm margins and a table of contents. Landscape gives the seven-column detail tables room for resource IDs, which
cannot wrap. The generated tables size their columns through the separator dashes, which pandoc reads as relative
widths. The SHA-256 of the Markdown goes into the PDF keywords. The committed `report/REPORT.pdf` is the only PDF
this repository publishes.

## Consequences

- `make verify` checks the PDF without Docker or pandoc: it reads the keywords with `pypdf` and compares the
  hash with the Markdown on disk.
- `make pdf` needs Docker. The image is duplicated in `scripts/build_pdf.py` and the arguments in both the script and
  `ci.yml`; when the shared workflow changes its pin, or either copy of the arguments changes, the other follows.
- PDF bytes differ between runs (timestamps), so the hash in the keywords, not the bytes, proves freshness.

## Alternatives considered

- **pandoc with Typst.** Byte-reproducible output, but a second engine next to the shared LaTeX job, so CI
  produced two different PDFs. An earlier revision used it.
- **Headless browser printing.** Needs a browser in CI, and its output varies between versions.

## Compliance

- `make check` runs `scripts/build_pdf.py --check`, and
  `tests/test_report.py::test_pdf_was_built_from_the_committed_markdown` runs the same check.
- The shared `report / pdf` check renders the Markdown with the same image and arguments and fails if the PDF is
  empty.
