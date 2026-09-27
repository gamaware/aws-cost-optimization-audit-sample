"""Evidence files and the report, both rendered from one Audit.

The report template holds prose only. Every number reaches the report through
a `{{ fact }}` or `{{ table:name }}` placeholder filled from `facts()` and
`tables()`, so the committed report can always be regenerated and checked.
"""

from __future__ import annotations

import csv
import io
import json
import re
from decimal import ROUND_HALF_UP, Decimal

from . import analysis
from .analysis import ACCOUNT_NAMES, Audit
from .model import D, pct, to_cents, usd

PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_:.-]+)\s*\}\}")
SERVICE_NAMES = {
    "AmazonEC2": "Amazon EC2 (instances, EBS, NAT)",
    "AmazonRDS": "Amazon RDS",
    "AmazonCloudFront": "Amazon CloudFront",
    "AmazonCloudWatch": "Amazon CloudWatch",
    "AmazonRedshift": "Amazon Redshift",
    "AmazonS3": "Amazon S3",
    "AWSDataTransfer": "Data transfer",
    "AmazonDynamoDB": "Amazon DynamoDB",
    "ComputeSavingsPlans": "Savings Plans fee",
    "AmazonElastiCache": "Amazon ElastiCache",
    "AWSLambda": "AWS Lambda",
    "AWSELB": "Elastic Load Balancing",
    "AmazonVPC": "Amazon VPC (public IPv4)",
}
TOP_SERVICES = 6


def _table(header: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    align = align or ["l"] * len(header)
    # pandoc sizes wide pipe tables by the dash count of each separator cell. Single-word cells (IDs, amounts,
    # code spans) cannot wrap in the PDF, so their columns get their full length; prose columns share the rest,
    # capped so that no column takes over. The + 2 covers cell padding.
    widths = []
    for i in range(len(header)):
        cells = [header[i]] + [r[i] for r in rows if r[i]]
        lengths = [len(c.replace("`", "").replace("**", "")) for c in cells]
        nowrap = all(" " not in c.replace("**", "") or c.startswith("`") for c in cells[1:])
        widths.append((max(lengths) if nowrap else min(max(lengths), 24)) + 2)
    sep = [("-" * w + ":") if a == "r" else "-" * w for w, a in zip(widths, align, strict=True)]

    def line(cells: list[str]) -> str:
        return "|" + "|".join(f" {c} " if c else " " for c in cells) + "|"

    return "\n".join([line(header), line(sep), *(line(r) for r in rows)])


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def hourly(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def short(resource: str) -> str:
    """Readable name for long ARNs: log groups keep their name, others keep the last segment."""
    if ":log-group:" in resource:
        return resource.split(":log-group:", 1)[1]
    return resource


def _change(old: Decimal, new: Decimal) -> str:
    return f"{usd(new - old)} ({pct((new - old) / old)})" if old else "new"


def _periods(audit: Audit) -> list[str]:
    return audit.ds.assumptions["trend_periods"]


def service_rows(audit: Audit) -> tuple[list[list[str]], list[list]]:
    ds = audit.ds
    periods = _periods(audit)
    first, last = periods[0], periods[-1]
    spend = analysis.spend_by(ds, "service")
    total = analysis.totals(ds)
    order = sorted(spend, key=lambda s: (-spend[s][last], s))
    md, raw = [], []
    for s in order:
        v = spend[s]
        raw.append([s, *[str(to_cents(v[p])) for p in periods], str(to_cents(v[last] - v[first]))])
    for s in order[:TOP_SERVICES]:
        v = spend[s]
        md.append(
            [SERVICE_NAMES[s], *[usd(v[p]) for p in periods], _change(v[first], v[last]), pct(v[last] / total[last])]
        )
    rest = order[TOP_SERVICES:]
    other = {p: sum((spend[s][p] for s in rest), Decimal(0)) for p in periods}
    md.append(
        [
            f"All other ({len(rest)} services)",
            *[usd(other[p]) for p in periods],
            _change(other[first], other[last]),
            pct(other[last] / total[last]),
        ]
    )
    md.append(
        [
            "**Total**",
            *[f"**{usd(total[p])}**" for p in periods],
            f"**{_change(total[first], total[last])}**",
            "**100.0%**",
        ]
    )
    return md, raw


def account_rows(audit: Audit) -> list[list[str]]:
    periods = _periods(audit)
    spend = analysis.spend_by(audit.ds, "account")
    total = analysis.totals(audit.ds)
    last = periods[-1]
    return [
        [
            f"`{a}` ({ACCOUNT_NAMES[a]})",
            *[usd(spend[a][p]) for p in periods],
            _change(spend[a][periods[0]], spend[a][last]),
            pct(spend[a][last] / total[last]),
        ]
        for a in sorted(spend, key=lambda a: -spend[a][last])
    ]


def movers(audit: Audit) -> list[tuple[str, Decimal]]:
    periods = _periods(audit)
    spend = analysis.spend_by(audit.ds, "service")
    delta = [(s, spend[s][periods[-1]] - spend[s][periods[0]]) for s in spend]
    return sorted(delta, key=lambda x: (-x[1], x[0]))


def facts(audit: Audit) -> dict[str, str]:
    ds = audit.ds
    periods = _periods(audit)
    total = analysis.totals(ds)
    first, last = periods[0], periods[-1]
    bill = total[last]
    cov = audit.coverage
    sz = audit.sizing
    f: dict[str, str] = {
        "period": ds.period,
        "first_period": first,
        "hours": str(ds.hours),
        "bill": usd(bill),
        "bill_first": usd(total[first]),
        "bill_growth": usd(bill - total[first]),
        "bill_growth_pct": pct((bill - total[first]) / total[first]),
        "savings_monthly": usd(audit.monthly_total),
        "savings_annual": usd(audit.monthly_total * 12),
        "savings_pct": pct(audit.monthly_total / bill),
        "bill_after": usd(bill - audit.monthly_total),
        "quick_monthly": usd(audit.monthly_of("Quick win")),
        "quick_annual": usd(audit.monthly_of("Quick win") * 12),
        "quick_count": str(sum(1 for r in audit.ranked if r.kind == "Quick win")),
        "planned_monthly": usd(audit.monthly_of("Planned work")),
        "planned_annual": usd(audit.monthly_of("Planned work") * 12),
        "planned_count": str(sum(1 for r in audit.ranked if r.kind == "Planned work")),
        "finding_count": str(len(audit.ranked)),
        "one_time_total": usd(audit.one_time_total()),
        "account_count": str(len({ln.account for ln in ds.lines})),
        "line_count": f"{len(ds.lines):,}",
        "service_count": str(len({ln.service for ln in ds.lines})),
        "sp_fee": usd(cov.sp_fee),
        "sp_covered_od": usd(cov.sp_covered_od),
        "sp_discount": pct(cov.sp_discount),
        "sp_utilization": pct(cov.sp_utilization),
        "sp_eligible_od": usd(cov.eligible_od),
        "sp_coverage": pct(cov.sp_coverage),
        "rds_instance_od": usd(cov.rds_instance_od),
        "rds_coverage": pct(cov.rds_coverage),
        "sp_baseline_hourly": hourly(sz.baseline_hourly_od),
        "sp_baseline_count": str(len(sz.baseline_rows)),
        "sp_target_share": pct(D(ds.assumptions["compute_savings_plan"]["coverage_target_of_steady_baseline"]), 0),
        "sp_target_hourly": hourly(sz.target_covered_hourly_od),
        "sp_commitment_hourly": hourly(sz.commitment_hourly),
        "sp_commitment_monthly": usd(sz.commitment_hourly * ds.hours),
        "sp_commitment_annual": usd(sz.commitment_hourly * ds.hours * 12),
        "sp_covered_monthly": usd(sz.covered_hourly_od * ds.hours),
        "sp_eligible_after": usd(analysis.post_change_eligible_od(audit)),
        "sp_coverage_after": pct(
            (cov.sp_covered_od + sz.covered_hourly_od * ds.hours) / analysis.post_change_eligible_od(audit)
        ),
        "rds_ri_discount": pct(D(ds.assumptions["rds_reserved_instances"]["discount"]), 0),
        "scheduled_hours": f"{analysis.findings.scheduled_hours(ds)}",
        "snapshot_days": str(ds.assumptions["idle"]["snapshot_age_threshold_days"]),
        "log_ratio": str(ds.assumptions["cloudwatch_logs"]["stored_to_ingested_ratio"]),
        "debug_share": pct(D(ds.assumptions["cloudwatch_logs"]["debug_share_of_order_api_ingest"]), 0),
        "s3_after_days": str(ds.assumptions["s3_lifecycle"]["transition_after_days"]),
        "s3_retrieval_gb": str(ds.assumptions["s3_lifecycle"]["expected_retrieval_gb_per_month"]),
    }
    for r in audit.ranked:
        k = r.finding.key
        f[f"{k}.id"] = r.fid
        f[f"{k}.rank"] = str(r.rank)
        f[f"{k}.monthly"] = usd(r.finding.monthly)
        f[f"{k}.annual"] = usd(r.finding.annual)
        f[f"{k}.one_time"] = usd(r.finding.one_time)
        f[f"{k}.count"] = str(len(r.finding.details))
        f[f"{k}.current"] = usd(sum((d.current for d in r.finding.details), Decimal(0)))
    f.update(_scenario_facts(audit))
    s3 = audit.by_key("s3-lifecycle").finding
    f["s3-lifecycle.payback_months"] = str((s3.one_time / s3.monthly).quantize(Decimal("0.1")))
    unattached = audit.by_key("unattached-ebs").finding
    f["unattached-ebs.payback_months"] = str((unattached.one_time / unattached.monthly).quantize(Decimal("0.1")))
    for n, (svc, delta) in enumerate(movers(audit)[:3], start=1):
        f[f"mover{n}"] = SERVICE_NAMES[svc]
        f[f"mover{n}.delta"] = usd(delta)
    top3 = audit.ranked[:3]
    for n, r in enumerate(top3, start=1):
        f[f"top{n}.title"] = r.finding.title
        f[f"top{n}.monthly"] = usd(r.finding.monthly)
        f[f"top{n}.id"] = r.fid
    for tc in analysis.tag_coverage(ds):
        f[f"tag.{tc.tag}"] = pct(tc.share)
        f[f"tag.{tc.tag}.untagged"] = usd(tc.untagged)
    kinds = analysis.untagged_by_kind(ds)
    for k, v in kinds.items():
        f[f"untagged.{k.replace(' ', '_')}"] = usd(v)
    return f


def _scenario_facts(audit: Audit) -> dict[str, str]:
    """Counts and settings the prose mentions, read from the data so the text cannot drift."""
    ds = audit.ds
    periods = _periods(audit)
    cfg = ds.assumptions

    def fleet(env: str, period: str) -> int:
        return len(
            {
                ln.resource
                for ln in ds.lines
                if ln.period == period
                and ln.usage_type.startswith("BoxUsage:")
                and ln.tag("application") == "order-api"
                and ln.tag("environment") == env
            }
        )

    threshold = cfg["idle"]["snapshot_age_threshold_days"]
    in_ami = {s for img in ds.images for s in img["SnapshotIds"]}
    old = [s for s in ds.snapshots if s["AgeDays"] > threshold]
    held = [s for s in old if any(t["Key"] == cfg["idle"]["snapshot_retention_tag_key"] for t in s["Tags"])]
    stg = next(r for r in ds.ec2_recs if r["instanceName"].startswith("stg-app"))
    stg_nat = [g for g in ds.nat_gateways if g["Environment"] == cfg["nat_consolidation"]["environment"]]
    stg_nat_ids = {g["NatGatewayId"] for g in stg_nat}
    nat_gb = [
        ln.usage
        for ln in ds.current()
        if ln.usage_type == "NatGateway-Bytes" and ln.resource.rsplit("/", 1)[-1] in stg_nat_ids
    ]
    retention = cfg["cloudwatch_logs"]["retention_days_by_class"]
    return {
        "app_count_first": str(fleet("prod", periods[0])),
        "app_count_last": str(fleet("prod", periods[-1])),
        "stg_count_first": str(fleet("staging", periods[0])),
        "stg_count_last": str(fleet("staging", periods[-1])),
        "snapshots_held": str(len(held)),
        "snapshots_in_ami": str(len([s for s in old if s["SnapshotId"] in in_ami])),
        "stg_cpu_max": f"{next(m['value'] for m in stg['utilizationMetrics'] if m['name'] == 'CPU'):g}%",
        "stg_nat_count": str(len(stg_nat)),
        "stg_nat_gb": f"{max(nat_gb):,}",
        "retention_application": str(retention["application"]),
        "retention_network": str(retention["network"]),
    }


def _detail_rows(audit: Audit, keys: list[str]) -> list[list[str]]:
    rows = []
    for key in keys:
        r = audit.by_key(key)
        for d in r.finding.details:
            rows.append(
                [
                    r.fid,
                    f"`{d.account}`",
                    f"`{d.resource}`",
                    d.description,
                    usd(d.current),
                    usd(d.target),
                    usd(d.saving),
                ]
            )
        if r.finding.adjustment:
            rows.append([r.fid, "", "", f"Less {r.finding.adjustment_note}", "", "", usd(r.finding.adjustment)])
    return rows


DETAIL_HEADER = ["ID", "Account", "Resource", "Detail", "Current/mo", "Target/mo", "Saving/mo"]
DETAIL_ALIGN = ["l", "l", "l", "l", "r", "r", "r"]


def tables(audit: Audit) -> dict[str, str]:
    ds = audit.ds
    periods = _periods(audit)
    svc_md, _ = service_rows(audit)
    t: dict[str, str] = {}
    t["services"] = _table(
        ["Service", *periods, f"Change {periods[0]} to {periods[-1]}", f"Share of {periods[-1]}"],
        svc_md,
        ["l", "r", "r", "r", "r", "r"],
    )
    t["accounts"] = _table(
        ["Account", *periods, f"Change {periods[0]} to {periods[-1]}", f"Share of {periods[-1]}"],
        account_rows(audit),
        ["l", "r", "r", "r", "r", "r"],
    )
    t["ranked"] = _table(
        ["Rank", "ID", "Recommendation", "Monthly", "Annual", "One-time cost", "Effort", "Risk", "Type"],
        [
            [
                str(r.rank),
                r.fid,
                r.finding.title,
                usd(r.finding.monthly),
                usd(r.finding.annual),
                usd(r.finding.one_time) if r.finding.one_time else "none",
                r.effort,
                r.risk,
                r.kind,
            ]
            for r in audit.ranked
        ]
        + [
            [
                "",
                "",
                "**Total**",
                f"**{usd(audit.monthly_total)}**",
                f"**{usd(audit.monthly_total * 12)}**",
                f"**{usd(audit.one_time_total())}**",
                "",
                "",
                "",
            ]
        ],
        ["r", "l", "l", "r", "r", "r", "l", "l", "l"],
    )
    for kind, name in (("Quick win", "quick"), ("Planned work", "planned")):
        t[name] = _table(
            ["ID", "Recommendation", "Monthly", "Why this effort and risk"],
            [[r.fid, r.finding.title, usd(r.finding.monthly), r.why] for r in audit.ranked if r.kind == kind],
            ["l", "l", "r", "l"],
        )
    t["idle"] = _table(
        DETAIL_HEADER,
        _detail_rows(audit, ["unattached-ebs", "old-snapshots", "idle-eip", "idle-load-balancers", "idle-instances"]),
        DETAIL_ALIGN,
    )
    t["rightsizing"] = _table(
        DETAIL_HEADER,
        _detail_rows(audit, ["rightsize-ec2", "rightsize-rds-prod", "rightsize-rds-staging", "schedule-staging"]),
        DETAIL_ALIGN,
    )
    t["storage"] = _table(
        DETAIL_HEADER,
        _detail_rows(audit, ["log-retention", "debug-logging", "s3-lifecycle", "nat-consolidation"]),
        DETAIL_ALIGN,
    )
    t["optimized"] = _table(
        ["Resource", "Current type", "Compute Optimizer finding", "Max CPU", "Max memory"],
        [
            [
                r["instanceName"],
                r["currentInstanceType"],
                r["finding"],
                f"{next(m['value'] for m in r['utilizationMetrics'] if m['name'] == 'CPU'):g}%",
                f"{next(m['value'] for m in r['utilizationMetrics'] if m['name'] == 'MEMORY'):g}%",
            ]
            for r in ds.ec2_recs
            if r["finding"] == "Optimized" and r["instanceName"].endswith("-01")
        ],
        ["l", "l", "l", "r", "r"],
    )
    cov = audit.coverage
    sz = audit.sizing
    t["coverage"] = _table(
        ["Measure", "Value"],
        [
            [f"Savings Plans eligible on-demand spend ({ds.period})", usd(cov.eligible_od)],
            ["Covered by the existing Compute Savings Plan", usd(cov.sp_covered_od)],
            ["Savings Plans coverage", pct(cov.sp_coverage)],
            ["Existing plan utilization", pct(cov.sp_utilization)],
            ["Observed Savings Plan discount (1 - fee / covered)", pct(cov.sp_discount)],
            [f"RDS instance-hour spend ({ds.period})", usd(cov.rds_instance_od)],
            ["RDS Reserved Instance coverage", pct(cov.rds_coverage)],
        ],
        ["l", "r"],
    )
    t["sp_sizing"] = _table(
        ["Step", "Value"],
        [
            [
                f"Steady post-change baseline ({len(sz.baseline_rows)} instances, on-demand per hour)",
                hourly(sz.baseline_hourly_od),
            ],
            ["Target covered on-demand per hour", hourly(sz.target_covered_hourly_od)],
            ["Commitment per hour (rounded down)", hourly(sz.commitment_hourly)],
            ["On-demand equivalent covered per hour", hourly(sz.covered_hourly_od)],
            ["Commitment per month", usd(sz.commitment_hourly * ds.hours)],
            ["Estimated saving per month", usd(audit.by_key("compute-savings-plan").finding.monthly)],
        ],
        ["l", "r"],
    )
    t["sp_baseline"] = _table(
        ["Account", "Instance", "Sized as", "On-demand per hour"],
        [
            [f"`{d.account}`", f"`{d.resource}`", d.description.split(" as ")[1], hourly(d.current)]
            for d in sz.baseline_rows
        ],
        ["l", "l", "l", "r"],
    )
    t["ri"] = _table(DETAIL_HEADER, _detail_rows(audit, ["rds-reserved-instances"]), DETAIL_ALIGN)
    t["tags"] = _table(
        ["Required tag", f"Share of {ds.period} cost tagged", "Untagged cost"],
        [[f"`{tc.tag}`", pct(tc.share), usd(tc.untagged)] for tc in analysis.tag_coverage(ds)],
        ["l", "r", "r"],
    )
    t["untagged"] = _table(
        ["Account", "Service", "Resource", f"{ds.period} cost"],
        [[f"`{a}`", SERVICE_NAMES[s], f"`{short(r)}`", usd(c)] for a, s, r, c in analysis.untagged_resources(ds)[:8]],
        ["l", "l", "l", "r"],
    )
    t["assumptions"] = _table(["Assumption", "Value", "Used by"], _assumption_rows(audit), ["l", "r", "l"])
    return t


def _assumption_rows(audit: Audit) -> list[list[str]]:
    a = audit.ds.assumptions
    ids = {r.finding.key: r.fid for r in audit.ranked}
    return [
        ["Hours in a month", str(a["hours_per_month"]), "all"],
        [
            "Staging schedule",
            f"{a['staging_schedule']['hours_per_day']} h x {a['staging_schedule']['days_per_week']} "
            f"days = {analysis.findings.scheduled_hours(audit.ds)} h/month",
            ids["schedule-staging"],
        ],
        ["Snapshot age threshold", f"{a['idle']['snapshot_age_threshold_days']} days", ids["old-snapshots"]],
        ["Rollback snapshot kept for", f"{a['idle']['rollback_snapshot_months']} month", ids["unattached-ebs"]],
        [
            "Compute Savings Plan coverage target",
            pct(D(a["compute_savings_plan"]["coverage_target_of_steady_baseline"]), 0) + " of the steady baseline",
            ids["compute-savings-plan"],
        ],
        ["Compute Savings Plan discount", pct(audit.coverage.sp_discount) + " (observed)", ids["compute-savings-plan"]],
        [
            "RDS Reserved Instance discount",
            pct(D(a["rds_reserved_instances"]["discount"]), 0) + " (planning figure)",
            ids["rds-reserved-instances"],
        ],
        [
            "CloudWatch Logs stored-to-ingested ratio",
            a["cloudwatch_logs"]["stored_to_ingested_ratio"],
            ids["log-retention"],
        ],
        [
            "Retention: application / network logs",
            " / ".join(f"{v} days" for v in a["cloudwatch_logs"]["retention_days_by_class"].values()),
            ids["log-retention"],
        ],
        [
            "DEBUG share of order-api log volume",
            pct(D(a["cloudwatch_logs"]["debug_share_of_order_api_ingest"]), 0),
            ids["debug-logging"],
        ],
        ["S3 transition age", f"{a['s3_lifecycle']['transition_after_days']} days", ids["s3-lifecycle"]],
        [
            "Expected Glacier Instant Retrieval reads",
            f"{a['s3_lifecycle']['expected_retrieval_gb_per_month']} GB/month",
            ids["s3-lifecycle"],
        ],
        ["Staging NAT gateways kept", str(a["nat_consolidation"]["keep_gateways"]), ids["nat-consolidation"]],
    ]


def evidence(audit: Audit) -> dict[str, str]:
    ds = audit.ds
    periods = _periods(audit)
    _, svc_raw = service_rows(audit)
    spend = analysis.spend_by(ds, "account")
    out = {
        "spend-by-service.csv": _csv(["service", *periods, "change_first_to_last"], svc_raw),
        "spend-by-account.csv": _csv(
            ["account", *periods], [[a, *[str(to_cents(spend[a][p])) for p in periods]] for a in sorted(spend)]
        ),
        "savings-ranked.csv": _csv(
            ["rank", "id", "key", "title", "monthly_usd", "annual_usd", "one_time_usd", "effort", "risk", "type"],
            [
                [
                    r.rank,
                    r.fid,
                    r.finding.key,
                    r.finding.title,
                    r.finding.monthly,
                    r.finding.annual,
                    r.finding.one_time,
                    r.effort,
                    r.risk,
                    r.kind,
                ]
                for r in audit.ranked
            ],
        ),
        "savings-detail.csv": _csv(
            ["id", "key", "account", "resource", "description", "current_usd", "target_usd", "saving_usd"],
            [
                [
                    r.fid,
                    r.finding.key,
                    d.account,
                    d.resource,
                    d.description,
                    to_cents(d.current),
                    to_cents(d.target),
                    to_cents(d.saving),
                ]
                for r in audit.ranked
                for d in r.finding.details
            ]
            + [
                [
                    r.fid,
                    r.finding.key,
                    "",
                    "adjustment",
                    r.finding.adjustment_note,
                    "",
                    "",
                    to_cents(r.finding.adjustment),
                ]
                for r in audit.ranked
                if r.finding.adjustment
            ],
        ),
        "tag-coverage.csv": _csv(
            ["tag", "tagged_usd", "untagged_usd", "share_tagged"],
            [
                [tc.tag, to_cents(tc.tagged), to_cents(tc.untagged), tc.share.quantize(Decimal("0.0001"))]
                for tc in analysis.tag_coverage(ds)
            ],
        ),
        "commitments.json": json.dumps(
            {
                "coverage": {k: str(v) for k, v in vars(audit.coverage).items()},
                "compute_savings_plan": {
                    "baseline_hourly_od": str(audit.sizing.baseline_hourly_od),
                    "target_covered_hourly_od": str(audit.sizing.target_covered_hourly_od),
                    "commitment_hourly": str(audit.sizing.commitment_hourly),
                    "covered_hourly_od": str(to_cents(audit.sizing.covered_hourly_od)),
                    "baseline_instances": [d.resource for d in audit.sizing.baseline_rows],
                },
            },
            indent=2,
        )
        + "\n",
    }
    out["facts.json"] = json.dumps(facts(audit), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return out


def render(template: str, audit: Audit) -> str:
    values = facts(audit)
    tbls = tables(audit)
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("table:"):
            name = key.split(":", 1)[1]
            if name in tbls:
                return tbls[name]
        elif key in values:
            return values[key]
        missing.append(key)
        return m.group(0)

    text = PLACEHOLDER.sub(sub, template)
    if missing:
        raise KeyError(f"unknown placeholders in report template: {sorted(set(missing))}")
    return text
