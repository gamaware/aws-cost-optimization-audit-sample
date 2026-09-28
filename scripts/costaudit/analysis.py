"""Spend breakdown, trend, tag coverage and the ranked savings list."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from . import commitments, findings
from .findings import Finding
from .model import Dataset, to_cents

ACCOUNT_NAMES = {"111122223333": "production", "444455556666": "staging", "123456789012": "shared services"}


def spend_by(ds: Dataset, attr: str) -> dict[str, dict[str, Decimal]]:
    """{key: {period: net cost}} for attr = 'service' or 'account'."""
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for ln in ds.lines:
        out[getattr(ln, attr)][ln.period] += ln.cost
    return out


def totals(ds: Dataset) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in ds.lines:
        out[ln.period] += ln.cost
    return out


@dataclass
class TagCoverage:
    tag: str
    tagged: Decimal
    untagged: Decimal

    @property
    def share(self) -> Decimal:
        return self.tagged / (self.tagged + self.untagged)


def tag_coverage(ds: Dataset) -> list[TagCoverage]:
    out = []
    for tag in ds.assumptions["required_tags"]:
        tagged = sum((ln.cost for ln in ds.current() if ln.tag(tag)), Decimal(0))
        untagged = sum((ln.cost for ln in ds.current() if not ln.tag(tag)), Decimal(0))
        out.append(TagCoverage(tag, tagged, untagged))
    return out


def untagged_by_kind(ds: Dataset) -> dict[str, Decimal]:
    """Cost with no application tag, split into what tagging can fix and what needs allocation rules."""
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in ds.current():
        if ln.tag("application"):
            continue
        if ln.line_type == "SavingsPlanRecurringFee":
            out["commitment fees"] += ln.cost
        elif not ln.resource:
            out["shared data transfer"] += ln.cost
        else:
            out["untagged resources"] += ln.cost
    return out


def untagged_resources(ds: Dataset) -> list[tuple[str, str, str, Decimal]]:
    by_res: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for ln in ds.current():
        if not ln.tag("application") and ln.resource and ln.line_type == "Usage":
            by_res[(ln.account, ln.service, ln.resource)] += ln.cost
    rows = [(a, s, r, c) for (a, s, r), c in by_res.items()]
    return sorted(rows, key=lambda x: (-x[3], x[2]))


@dataclass
class Ranked:
    rank: int
    fid: str
    finding: Finding
    effort: str
    risk: str
    why: str

    @property
    def kind(self) -> str:
        return "Quick win" if self.effort == "Low" and self.risk == "Low" else "Planned work"


@dataclass
class Audit:
    ds: Dataset
    ranked: list[Ranked]
    sizing: commitments.SavingsPlanSizing
    coverage: commitments.Coverage

    @property
    def monthly_total(self) -> Decimal:
        return sum((r.finding.monthly for r in self.ranked), Decimal(0))

    def monthly_of(self, kind: str) -> Decimal:
        return sum((r.finding.monthly for r in self.ranked if r.kind == kind), Decimal(0))

    def one_time_total(self) -> Decimal:
        return sum((r.finding.one_time for r in self.ranked), Decimal(0))

    def by_key(self, key: str) -> Ranked:
        return next(r for r in self.ranked if r.finding.key == key)


def run(ds: Dataset) -> Audit:
    base = findings.all_findings(ds)
    sizing = commitments.size_savings_plan(ds, base)
    every = [*base, commitments.savings_plan_finding(ds, sizing), commitments.rds_ri_finding(ds)]
    ids = {f.key: f"SAV-{n:02d}" for n, f in enumerate(every, start=1)}
    ordered = sorted(every, key=lambda f: (-f.monthly, ids[f.key]))
    ratings = ds.assumptions["ratings"]
    ranked = [
        Ranked(n, ids[f.key], f, ratings[f.key]["effort"], ratings[f.key]["risk"], ratings[f.key]["why"])
        for n, f in enumerate(ordered, start=1)
    ]
    return Audit(ds, ranked, sizing, commitments.coverage(ds))


def post_change_eligible_od(audit: Audit) -> Decimal:
    """Monthly Savings Plan eligible on-demand spend after the EC2 changes land."""
    removed = Decimal(0)
    for key in ("rightsize-ec2", "schedule-staging"):
        removed += audit.by_key(key).finding.monthly
    idle = audit.by_key("idle-instances").finding
    removed += sum((d.current for d in idle.details if d.resource.startswith("i-")), Decimal(0))
    return to_cents(audit.coverage.eligible_od - removed)
