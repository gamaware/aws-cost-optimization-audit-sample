"""The synthetic exports are reproducible, internally consistent and fictional."""

import csv
import ipaddress
import re
from decimal import Decimal
from pathlib import Path

import generate_synthetic
from costaudit.model import ROOT

SYNTHETIC = ROOT / "data" / "synthetic"
DOC_ACCOUNTS = {"111122223333", "444455556666", "123456789012"}


def test_generator_reproduces_committed_files():
    for rel, content in generate_synthetic.outputs().items():
        assert (SYNTHETIC / rel).read_text(encoding="utf-8") == content, f"{rel} differs; run make data"


def test_no_extra_files_in_synthetic_data():
    committed = {str(p.relative_to(SYNTHETIC)) for p in SYNTHETIC.rglob("*") if p.is_file()}
    assert committed == set(generate_synthetic.outputs())


def _all_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "data").rglob("*") if p.is_file())


def test_only_aws_documentation_account_ids():
    found = set(re.findall(r"(?<![\w-])\d{12}(?![\w-])", _all_text()))  # skips UUID segments
    assert found == DOC_ACCOUNTS


def test_only_documentation_ip_addresses():
    doc_net = ipaddress.ip_network("203.0.113.0/24")  # RFC 5737 TEST-NET-3
    ips = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", _all_text())
    assert ips, "expected the idle Elastic IP fixtures"
    assert all(ipaddress.ip_address(ip) in doc_net for ip in ips)


def test_cur_has_three_periods_and_expected_columns(ds):
    assert {ln.period for ln in ds.lines} == {"M1", "M2", "M3"}
    with (SYNTHETIC / "cur" / "cost-and-usage.csv").open() as fh:
        assert csv.DictReader(fh).fieldnames == generate_synthetic.COLUMNS


def test_savings_plan_negation_offsets_covered_usage(ds):
    for period in ("M1", "M2", "M3"):
        covered = sum(ln.cost for ln in ds.lines if ln.period == period and ln.line_type == "SavingsPlanCoveredUsage")
        negated = sum(ln.cost for ln in ds.lines if ln.period == period and ln.line_type == "SavingsPlanNegation")
        assert covered == -negated == Decimal("560.64")


def test_every_flagged_resource_is_billed(ds):
    billed = {ln.resource for ln in ds.current()}
    billed_names = {r.split("/")[-2] if "/app/" in r else r.rsplit("/", 1)[-1] for r in billed}
    for check, resources in ds.ta_checks.items():
        for r in resources:
            assert r["resourceId"] in billed or r["resourceId"] in billed_names, (check, r["resourceId"])
    for rec in ds.ec2_recs:
        assert rec["instanceArn"].rsplit("/", 1)[1] in billed
    for rec in ds.rds_recs:
        assert rec["resourceArn"] in billed


def test_log_group_inventory_matches_billed_usage(ds):
    for g in ds.log_groups:
        lines = [ln for ln in ds.current() if ln.resource.endswith(f"log-group:{g['logGroupName']}")]
        ingest = next(ln.usage for ln in lines if ln.usage_type == "DataProcessing-Bytes")
        stored = next(ln.usage for ln in lines if ln.usage_type == "TimedStorage-ByteHrs")
        assert (ingest, stored) == (Decimal(g["monthlyIngestGB"]), Decimal(g["storedGB"]))


def test_s3_age_report_matches_billed_storage(ds):
    total = sum(Decimal(b["size_gb"]) for b in ds.s3_age)
    billed = next(ln.usage for ln in ds.current() if ln.resource == "harbor-goods-app-logs")
    assert total == billed


def test_generator_is_executable():
    path = Path(generate_synthetic.__file__)
    assert path.read_text().startswith("#!/usr/bin/env python3")
