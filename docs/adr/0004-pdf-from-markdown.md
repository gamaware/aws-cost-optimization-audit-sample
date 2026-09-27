# ADR 0004: Build the PDF from the Markdown with pandoc and Typst

## Status

Accepted

## Context

Clients expect a PDF; reviewers want a diffable source. Two hand-maintained documents drift apart. A
LaTeX toolchain is heavy to install locally and in CI.

## Decision

`report/REPORT.md` is canonical. `scripts/build_pdf.py` converts it to Typst with pandoc and compiles it
with the pinned `typst` Python package, using only bundled fonts and no creation date, so the same input
always gives the same bytes. The SHA-256 of the Markdown goes into the PDF keywords.

## Consequences

- `make verify` checks the PDF without pandoc or Typst: it reads the keywords with `pypdf` and compares
  the hash with the Markdown on disk.
- Layout is plain but readable. Wide tables get column widths from the Markdown content.
- Building the PDF needs pandoc 3.11 on the machine. CI installs that exact version, checksum-verified.

## Alternatives considered

- **pandoc with LaTeX.** Better typography, but a much larger toolchain.
- **Headless browser printing.** Needs a browser in CI, and its output varies between versions.

## Compliance

- `make check` runs `scripts/build_pdf.py --check`, and
  `tests/test_report.py::test_pdf_was_built_from_the_committed_markdown` runs the same check.
- The CI report job rebuilds the PDF with pandoc 3.11 and fails if the result differs from the commit.
