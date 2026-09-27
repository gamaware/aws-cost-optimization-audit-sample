"""Run the Harbor Goods cost audit offline and write, or check, its outputs.

    PYTHONPATH=scripts python -m costaudit build    # write evidence/ and report/REPORT.md
    PYTHONPATH=scripts python -m costaudit check    # fail if committed outputs differ from a fresh run
    PYTHONPATH=scripts python -m costaudit summary  # print the ranked savings list

Inputs: data/synthetic/ and data/assumptions.json. No AWS access is needed.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from . import analysis, model, report

ROOT = model.ROOT
TEMPLATE = ROOT / "report" / "REPORT.template.md"
REPORT = ROOT / "report" / "REPORT.md"
EVIDENCE = ROOT / "evidence"


def outputs() -> dict[Path, str]:
    audit = analysis.run(model.load(ROOT))
    files = {EVIDENCE / name: text for name, text in report.evidence(audit).items()}
    files[REPORT] = report.render(TEMPLATE.read_text(encoding="utf-8"), audit)
    return files


def build() -> int:
    for path, text in outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


def check() -> int:
    stale = 0
    for path, text in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != text:
            stale += 1
            rel = str(path.relative_to(ROOT))
            sys.stdout.writelines(
                difflib.unified_diff(
                    current.splitlines(True), text.splitlines(True), f"committed/{rel}", f"generated/{rel}", n=1
                )
            )
    if stale:
        print(f"\n{stale} output file(s) are stale. Run `make evidence` and commit the result.", file=sys.stderr)
        return 1
    print("evidence/ and report/REPORT.md match a fresh run of the audit")
    return 0


def summary() -> int:
    audit = analysis.run(model.load(ROOT))
    for r in audit.ranked:
        print(f"{r.rank:>2}  {r.fid}  {model.usd(r.finding.monthly):>10}/month  {r.kind:<12}  {r.finding.title}")
    print(f"    total   {model.usd(audit.monthly_total):>10}/month")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "check", "summary"])
    args = parser.parse_args()
    return {"build": build, "check": check, "summary": summary}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
