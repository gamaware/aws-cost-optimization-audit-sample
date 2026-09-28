#!/usr/bin/env python3
"""Render report/REPORT.md to report/REPORT.pdf, or check that the PDF is current.

    python scripts/build_pdf.py          # build: pandoc with LaTeX, in the shared report workflow's image
    python scripts/build_pdf.py --check  # fail if REPORT.pdf was not built from the current REPORT.md

The build runs the same pinned pandoc/latex image and arguments as the shared `report` workflow in
gamaware/.github, with the arguments ci.yml passes to it, so the committed PDF and the CI artifact
come from one engine. It needs Docker.

The SHA-256 of REPORT.md is written into the PDF keywords. The check compares
that value with the Markdown on disk, so it needs neither Docker nor pandoc and
does not depend on byte-identical PDF output across runs.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "report" / "REPORT.md"
TARGET = ROOT / "report" / "REPORT.pdf"
KEY_PREFIX = "report-md-sha256:"
# Keep in step with PANDOC_IMAGE in gamaware/.github report.yml and the pandoc-args in .github/workflows/ci.yml.
# Landscape A4 gives the seven-column detail tables room for resource IDs, which cannot wrap.
PANDOC_IMAGE = "pandoc/latex:3.11@sha256:cdbf139f607237498b412b3aa051008311d69b88006ab47550efba357af3b277"
PANDOC_ARGS = [
    "--pdf-engine=xelatex",
    "-V",
    "papersize=a4",
    "-V",
    "geometry:margin=1.8cm",
    "-V",
    "geometry:landscape",
    "--toc",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> int:
    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform=linux/amd64",
        f"--user={os.getuid()}:{os.getgid()}",
        "--env=HOME=/tmp",
        f"--volume={ROOT}:/data",
        "--workdir=/data/report",
        PANDOC_IMAGE,
        SOURCE.name,
        *PANDOC_ARGS,
        f"--metadata=keywords:{KEY_PREFIX}{digest(SOURCE)}",
        f"--output={TARGET.name}",
    ]
    subprocess.run(cmd, check=True)
    print(f"wrote {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size:,} bytes)")
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
