"""Savings Plans and Reserved Instance coverage, and the commitments to buy.

Commitments are sized on usage that remains after the other findings, so the
savings never count the same dollar twice: rightsized types, scheduled and idle
instances, and resources without owner tags are all out of the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .findings import Detail, Finding, floor_to, rds_target_cost
from .model import D, Dataset


@dataclass
class Coverage:
    sp_fee: Decimal
    sp_covered_od: Decimal
    sp_discount: Decimal
    sp_utilization: Decimal
    eligible_od: Decimal
    sp_coverage: Decimal
    rds_instance_od: Decimal
    rds_reserved_od: Decimal
    rds_coverage: Decimal


def coverage(ds: Dataset) -> Coverage:
    cur = ds.current()
    fee = sum((ln.cost for ln in cur if ln.line_type == "SavingsPlanRecurringFee"), Decimal(0))
    covered = sum((ln.od_cost for ln in cur if ln.line_type == "SavingsPlanCoveredUsage"), Decimal(0))
    eligible = sum(
        (
            ln.od_cost
            for ln in cur
            if (ln.service == "AmazonEC2" and ln.usage_type.startswith("BoxUsage:")) or ln.service == "AWSLambda"
        ),
        Decimal(0),
    )
    rds_hours = [ln for ln in cur if ln.service == "AmazonRDS" and "Usage:db." in ln.usage_type]
    rds_od = sum((ln.od_cost for ln in rds_hours), Decimal(0))
    rds_ri = sum((ln.od_cost for ln in rds_hours if ln.pricing_term == "Reserved"), Decimal(0))
    if len(ds.savings_plans) != 1 or not covered:
        # The Savings Plan discount is observed on the existing plan. With none (or several), set an explicit
        # discount in assumptions.json and extend this function rather than guessing.
        raise ValueError("expected exactly one existing Savings Plan with covered usage in the analysis period")
    utilization = D(ds.savings_plans[0]["utilizationPercentage"]) / 100
    return Coverage(
        sp_fee=fee,
        sp_covered_od=covered,
        sp_discount=1 - fee / covered,
        sp_utilization=utilization,
        eligible_od=eligible,
        sp_coverage=covered / eligible,
        rds_instance_od=rds_od,
        rds_reserved_od=rds_ri,
        rds_coverage=rds_ri / rds_od if rds_od else Decimal(0),
    )


@dataclass
class SavingsPlanSizing:
    baseline_hourly_od: Decimal
    target_covered_hourly_od: Decimal
    commitment_hourly: Decimal
    covered_hourly_od: Decimal
    baseline_rows: list[Detail]


def size_savings_plan(ds: Dataset, done: list[Finding]) -> SavingsPlanSizing:
    cfg = ds.assumptions["compute_savings_plan"]
    removed = {r for f in done if f.key in ("schedule-staging", "idle-instances") for r in f.resources}
    resized = {}
    for rec in ds.ec2_recs:
        if rec["finding"] == "Overprovisioned":
            opt = next(o for o in rec["recommendationOptions"] if o["rank"] == 1)
            resized[rec["instanceArn"].rsplit("/", 1)[1]] = opt["instanceType"]
    periods = ds.assumptions["trend_periods"]
    present: dict[str, set[str]] = {}
    for ln in ds.lines:
        if ln.usage_type.startswith("BoxUsage:") and ln.line_type == "Usage":
            present.setdefault(ln.resource, set()).add(ln.period)
    rows = []
    for ln in ds.current():
        if not ln.usage_type.startswith("BoxUsage:") or ln.line_type != "Usage" or ln.resource in removed:
            continue
        if present[ln.resource] != set(periods):
            continue  # not steady across the whole trend window
        if cfg["baseline_excludes_untagged_resources"] and not ln.tag("application"):
            continue
        itype = resized.get(ln.resource, ln.instance_type)
        hourly = ds.price("ec2_hourly", itype)
        rows.append(Detail(ln.account, ln.resource, f"{ln.tag('Name')} as {itype}", hourly, Decimal(0)))
    baseline = sum((r.current for r in rows), Decimal(0))
    cov = coverage(ds)
    target = baseline * D(cfg["coverage_target_of_steady_baseline"])
    commitment = floor_to(target * (1 - cov.sp_discount), D(cfg["commitment_increment"]))
    covered = commitment / (1 - cov.sp_discount)
    return SavingsPlanSizing(baseline, target, commitment, covered, rows)


def savings_plan_finding(ds: Dataset, sizing: SavingsPlanSizing) -> Finding:
    f = Finding(
        "compute-savings-plan",
        "Buy a one-year Compute Savings Plan for the steady EC2 baseline",
        "commitment",
        basis="On-demand equivalent the new commitment covers, minus the commitment, over the hours in a month.",
    )
    covered_month = sizing.covered_hourly_od * ds.hours
    commit_month = sizing.commitment_hourly * ds.hours
    payer = ds.savings_plans[0]["savingsPlanArn"].split(":")[4]
    f.details.append(
        Detail(
            payer,
            "new Compute Savings Plan",
            f"commitment {sizing.commitment_hourly} USD/hour",
            covered_month,
            commit_month,
        )
    )
    return f


def rds_ri_finding(ds: Dataset) -> Finding:
    cfg = ds.assumptions["rds_reserved_instances"]
    discount = D(cfg["discount"])
    env_of = {ln.resource: ln.tag("environment") for ln in ds.current() if ln.service == "AmazonRDS"}
    reserved = {ln.resource for ln in ds.current() if ln.service == "AmazonRDS" and ln.pricing_term == "Reserved"}
    periods = set(ds.assumptions["trend_periods"])
    seen: dict[str, set[str]] = {}
    for ln in ds.lines:
        if ln.service == "AmazonRDS":
            seen.setdefault(ln.resource, set()).add(ln.period)
    f = Finding(
        "rds-reserved-instances",
        "Buy one-year RDS Reserved Instances for production after the resize",
        "commitment",
        basis="Post-rightsizing instance-hour cost (storage excluded) x the planning discount.",
    )
    for rec in ds.rds_recs:
        arn = rec["resourceArn"]
        if env_of.get(arn) not in cfg["environments"] or arn in reserved or seen.get(arn) != periods:
            continue  # other environments, already reserved, or not steady across the trend window
        if rec["instanceFinding"] == "Overprovisioned":
            opt = next(o for o in rec["instanceRecommendationOptions"] if o["rank"] == 1)
            cls, multi = opt["dbInstanceClass"], opt["multiAZ"]
        else:
            cls, multi = rec["currentDBInstanceClass"], rec["multiAZ"]
        od = rds_target_cost(ds, cls, multi, Decimal(0))
        name = rec["resourceArn"].rsplit(":", 1)[1]
        f.details.append(
            Detail(rec["accountId"], name, f"{cls} {'Multi-AZ' if multi else 'Single-AZ'}", od, od * (1 - discount))
        )
    return f
