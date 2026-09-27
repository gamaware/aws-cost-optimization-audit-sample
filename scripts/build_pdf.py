#!/usr/bin/env python3
"""Render report/REPORT.md to report/REPORT.pdf, or check that the PDF is current.

    python scripts/build_pdf.py          # build: pandoc (Markdown to Typst), then Typst to PDF
    python scripts/build_pdf.py --check  # fail if REPORT.pdf was not built from the current REPORT.md

The SHA-256 of REPORT.md is written into the PDF keywords. The check compares
that value with the Markdown on disk, so it needs neither pandoc nor Typst and
does not depend on byte-identical PDF output across tool versions.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "report" / "REPORT.md"
TARGET = ROOT / "report" / "REPORT.pdf"
KEY_PREFIX = "report-md-sha256:"
TABLE_STYLE = """#set table(
  inset: 4pt,
  fill: (_, y) => if y == 0 { luma(232) },
  stroke: (_, y) => (bottom: if y == 0 { 0.6pt } else { 0.3pt + luma(200) }),
)
#show table.cell.where(y: 0): strong
#show table: set text(size: 7.5pt)
#show table: set par(justify: false)
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def column_specs(markdown: str) -> list[str]:
    """One Typst `columns:` value per Markdown table.

    Short columns and identifier columns (all code spans, which cannot wrap) fit their content;
    long prose columns share the remaining width in proportion to their longest cell.
    """
    specs: list[str] = []
    widths: list[int] | None = None
    fixed: list[bool] = []
    for line in [*markdown.splitlines(), ""]:
        if line.startswith("|"):
            cells = re.split(r"\s*\|\s*", line.strip()[1:-1].strip())
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator row
            lengths = [len(c.replace("`", "").replace("**", "")) for c in cells]
            code = [c == "" or (c.startswith("`") and c.endswith("`")) for c in cells]
            if widths is None:  # header row: its text does not decide the width
                widths, fixed = [0] * len(cells), [True] * len(cells)
                continue
            widths = [max(a, b) for a, b in zip(widths, lengths, strict=True)]
            fixed = [a and b for a, b in zip(fixed, code, strict=True)]
        elif widths is not None:
            cols = ["auto" if f or w <= 16 else f"{min(w, 90) // 10 + 1}fr" for w, f in zip(widths, fixed, strict=True)]
            specs.append("(" + ", ".join(cols) + ",)")
            widths = None
    return specs


def size_columns(typ: str, markdown: str) -> str:
    specs = iter(column_specs(markdown))
    return re.sub(r"columns: \d+,", lambda _: f"columns: {next(specs)},", typ)


def build() -> int:
    import typst  # dev dependency, imported here so --check works without it

    text = SOURCE.read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    if not first.startswith("# "):
        print(f"{SOURCE} must start with a level-1 title", file=sys.stderr)
        return 1
    cmd = [
        "pandoc",
        "--from=gfm",
        "--to=typst",
        "--standalone",
        f"--metadata=title:{first[2:].strip()}",
        f"--metadata=keywords:{KEY_PREFIX}{digest(SOURCE)}",
        "--variable=papersize:a4",
        "--variable=margin.x:1.4cm",
        "--variable=margin.y:1.8cm",
        "--variable=fontsize:9pt",
    ]
    typ = subprocess.run(cmd, input=body, capture_output=True, text=True, check=True).stdout
    # No creation date in the PDF, so the same Markdown gives byte-identical output.
    typ = "#set document(date: none)\n" + typ
    # Left-align tables and give them a shaded header row and light row rules.
    typ = typ.replace("align(center)[#table(", "align(left)[#table(")
    typ = typ.replace("#show: doc => conf(", TABLE_STYLE + "#show: doc => conf(", 1)
    typ = size_columns(typ, body)
    pdf = typst.compile(typ.encode("utf-8"), root=str(ROOT), ignore_system_fonts=True)
    TARGET.write_bytes(pdf)
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(pdf):,} bytes)")
    return 0


def check() -> int:
    from pypdf import PdfReader

    if not TARGET.exists():
        print(f"{TARGET.relative_to(ROOT)} is missing. Run `make pdf`.", file=sys.stderr)
        return 1
    keywords = (PdfReader(TARGET).metadata or {}).get("/Keywords", "")
    expected = f"{KEY_PREFIX}{digest(SOURCE)}"
    if expected not in str(keywords):
        print(f"{TARGET.relative_to(ROOT)} was built from a different REPORT.md. Run `make pdf`.", file=sys.stderr)
        return 1
    print("report/REPORT.pdf matches report/REPORT.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    return check() if parser.parse_args().check else build()


if __name__ == "__main__":
    sys.exit(main())
