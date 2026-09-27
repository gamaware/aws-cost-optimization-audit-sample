"""The committed report, evidence and PDF are exactly what the data produces."""

import re
import subprocess
import sys

from costaudit import __main__ as cli
from costaudit import report
from costaudit.model import ROOT

TEMPLATE = ROOT / "report" / "REPORT.template.md"
# Numbers that are policy targets, not results, and may appear literally in the prose.
ALLOWED_LITERALS = {"95%"}


def test_committed_outputs_match_a_fresh_run():
    for path, text in cli.outputs().items():
        assert path.read_text(encoding="utf-8") == text, f"{path.relative_to(ROOT)} is stale; run make evidence"


def test_template_has_no_hand_typed_money_or_percentages():
    prose = report.PLACEHOLDER.sub("", TEMPLATE.read_text(encoding="utf-8"))
    literals = set(re.findall(r"\$\s?\d[\d,.]*|\d[\d,.]*\s?%", prose))
    assert literals <= ALLOWED_LITERALS


def test_every_placeholder_resolves(audit):
    report.render(TEMPLATE.read_text(encoding="utf-8"), audit)  # raises KeyError on an unknown key


def test_report_states_it_is_fictional():
    text = (ROOT / "report" / "REPORT.md").read_text(encoding="utf-8")
    assert text.count("Fictional sample") >= 2  # title block and footer
    assert "estimate" in text


def test_report_money_matches_ranked_evidence(audit):
    text = (ROOT / "report" / "REPORT.md").read_text(encoding="utf-8")
    for r in audit.ranked:
        row = next(line for line in text.splitlines() if line.startswith(f"| {r.rank} | {r.fid} |"))
        assert f"${r.finding.monthly:,.2f}" in row and f"${r.finding.annual:,.2f}" in row


def test_pdf_was_built_from_the_committed_markdown():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_pdf.py"), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_movers_match_the_prose(audit):
    # The template explains the top three movers in this order.
    assert [s for s, _ in report.movers(audit)[:3]] == ["AmazonEC2", "AmazonCloudWatch", "AWSDataTransfer"]


def test_readme_headline_figures_match_the_report(audit):
    from costaudit import report as rpt

    facts = rpt.facts(audit)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for key in (
        "bill",
        "bill_growth_pct",
        "savings_monthly",
        "savings_annual",
        "savings_pct",
        "quick_monthly",
        "planned_monthly",
        "top1.monthly",
        "top2.monthly",
        "top3.monthly",
        "tag.cost-center",
        "sp_coverage",
    ):
        assert facts[key] in readme, f"README is missing {key} = {facts[key]}"
