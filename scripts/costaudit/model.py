"""Loading the synthetic exports and the shared money helpers."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CENT = Decimal("0.01")
TAG_COLUMNS = {
    "application": "resource_tags_user_application",
    "environment": "resource_tags_user_environment",
    "cost-center": "resource_tags_user_cost_center",
}


def D(value) -> Decimal:
    """Decimal from str/int/Decimal. Floats are rejected so no binary rounding sneaks in."""
    if isinstance(value, float):
        raise TypeError(f"use a string, not a float: {value!r}")
    return Decimal(str(value))


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def usd(value: Decimal) -> str:
    q = to_cents(value)
    sign = "-" if q < 0 else ""
    return f"{sign}${abs(q):,.2f}"


def pct(value: Decimal, places: int = 1) -> str:
    q = (value * 100).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{q}%"


@dataclass(frozen=True)
class Line:
    period: str
    account: str
    line_type: str
    service: str
    resource: str
    usage_type: str
    instance_type: str
    pricing_term: str
    usage: Decimal
    od_cost: Decimal
    cost: Decimal
    tags: dict = field(hash=False, compare=False)

    def tag(self, key: str) -> str:
        return self.tags.get(key, "")


@dataclass
class Dataset:
    root: Path
    assumptions: dict
    lines: list[Line]
    ec2_recs: list[dict]
    rds_recs: list[dict]
    ta_checks: dict[str, list[dict]]
    snapshots: list[dict]
    images: list[dict]
    log_groups: list[dict]
    nat_gateways: list[dict]
    savings_plans: list[dict]
    s3_age: list[dict]

    @property
    def period(self) -> str:
        return self.assumptions["analysis_period"]

    @property
    def hours(self) -> Decimal:
        return D(self.assumptions["hours_per_month"])

    def price(self, *path: str) -> Decimal:
        node = self.assumptions["unit_prices"]
        for key in path:
            node = node[key]
        return D(node)

    def current(self) -> list[Line]:
        return [ln for ln in self.lines if ln.period == self.period]

    def cost_by_resource(self, period: str | None = None) -> dict[str, Decimal]:
        period = period or self.period
        out: dict[str, Decimal] = defaultdict(Decimal)
        for ln in self.lines:
            if ln.period == period:
                out[ln.resource] += ln.cost
        return dict(out)  # a plain dict, so a resource missing from the CUR raises KeyError

    def usage_line(self, resource_suffix: str, usage_type: str) -> Line:
        """The single analysis-period line for a resource and usage type; fails loudly if absent."""
        found = [ln for ln in self.current() if ln.resource.endswith(resource_suffix) and ln.usage_type == usage_type]
        if len(found) != 1:
            raise LookupError(f"expected one {usage_type} line for {resource_suffix}, found {len(found)}")
        return found[0]


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load(root: Path = ROOT) -> Dataset:
    syn = root / "data" / "synthetic"
    lines = []
    with (syn / "cur" / "cost-and-usage.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            lines.append(
                Line(
                    period=r["bill_billing_period"],
                    account=r["line_item_usage_account_id"],
                    line_type=r["line_item_line_item_type"],
                    service=r["product_servicecode"],
                    resource=r["line_item_resource_id"],
                    usage_type=r["line_item_usage_type"],
                    instance_type=r["product_instance_type"],
                    pricing_term=r["pricing_term"],
                    usage=D(r["line_item_usage_amount"]),
                    od_cost=D(r["pricing_public_on_demand_cost"]),
                    cost=D(r["line_item_unblended_cost"]),
                    tags={k: r[col] for k, col in TAG_COLUMNS.items()} | {"Name": r["resource_tags_user_name"]},
                )
            )
    ta = _json(syn / "trusted-advisor" / "cost-optimizing-checks.json")
    with (syn / "inventory" / "s3-storage-by-age.csv").open(encoding="utf-8", newline="") as fh:
        s3_age = list(csv.DictReader(fh))
    return Dataset(
        root=root,
        assumptions=_json(root / "data" / "assumptions.json"),
        lines=lines,
        ec2_recs=_json(syn / "compute-optimizer" / "ec2-instance-recommendations.json")["instanceRecommendations"],
        rds_recs=_json(syn / "compute-optimizer" / "rds-recommendations.json")["rdsDBRecommendations"],
        ta_checks={c["name"]: c["flaggedResources"] for c in ta["checks"]},
        snapshots=_json(syn / "inventory" / "ebs-snapshots.json")["Snapshots"],
        images=_json(syn / "inventory" / "images.json")["Images"],
        log_groups=_json(syn / "inventory" / "cloudwatch-log-groups.json")["logGroups"],
        nat_gateways=_json(syn / "inventory" / "nat-gateways.json")["NatGateways"],
        savings_plans=_json(syn / "inventory" / "savings-plans.json")["savingsPlans"],
        s3_age=s3_age,
    )
