"""Savings findings: idle resources, rightsizing, scheduling, storage and logs.

Every current cost comes from the Cost and Usage Report for the analysis period.
Every target cost comes from a unit price in data/assumptions.json. Each finding
keeps its per-resource detail rows so the evidence files show the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from .model import D, Dataset, pct, to_cents


@dataclass
class Detail:
    account: str
    resource: str
    description: str
    current: Decimal
    target: Decimal

    @property
    def saving(self) -> Decimal:
        return self.current - self.target


@dataclass
class Finding:
    key: str  # rating key in assumptions.json
    title: str
    group: str  # idle | rightsizing | usage | commitment
    details: list[Detail] = field(default_factory=list)
    one_time: Decimal = Decimal(0)
    adjustment: Decimal = Decimal(0)  # added to the detail sum, e.g. retrieval fees
    adjustment_note: str = ""
    basis: str = ""

    @property
    def monthly(self) -> Decimal:
        return to_cents(sum((x.saving for x in self.details), Decimal(0)) + self.adjustment)

    @property
    def annual(self) -> Decimal:
        return self.monthly * 12

    @property
    def resources(self) -> list[str]:
        return [x.resource for x in self.details]


def _flagged(ds: Dataset, check: str) -> list[dict]:
    return ds.ta_checks.get(check, [])


# --- Idle and unattached -------------------------------------------------------
def unattached_volumes(ds: Dataset) -> Finding:
    costs = ds.cost_by_resource()
    f = Finding(
        "unattached-ebs",
        "Delete unattached EBS volumes after a rollback snapshot",
        "idle",
        basis="Current cost of each volume in the analysis period; target cost is zero.",
    )
    gb_total = Decimal(0)
    for r in _flagged(ds, "Underutilized Amazon EBS Volumes"):
        meta = r["metadata"]
        if meta.get("state") != "available":
            continue
        gb_total += D(meta["sizeGiB"])
        f.details.append(
            Detail(
                r["accountId"],
                r["resourceId"],
                f"{meta['volumeType']}, {meta['sizeGiB']:,} GiB, {meta['note']}",
                costs[r["resourceId"]],
                Decimal(0),
            )
        )
    months = D(ds.assumptions["idle"]["rollback_snapshot_months"])
    f.one_time = to_cents(gb_total * ds.price("ebs_snapshot_gb_month") * months)
    return f


def idle_eips(ds: Dataset) -> Finding:
    costs = ds.cost_by_resource()
    f = Finding(
        "idle-eip",
        "Release unassociated Elastic IP addresses",
        "idle",
        basis="Idle public IPv4 hours billed in the analysis period.",
    )
    for r in _flagged(ds, "Unassociated Elastic IP Addresses"):
        f.details.append(
            Detail(
                r["accountId"],
                r["resourceId"],
                f"public IP {r['metadata']['publicIp']}",
                costs[r["resourceId"]],
                Decimal(0),
            )
        )
    return f


def idle_load_balancers(ds: Dataset) -> Finding:
    f = Finding(
        "idle-load-balancers",
        "Delete idle load balancers",
        "idle",
        basis="Load balancer hours and LCUs billed in the analysis period.",
    )
    names = {r["resourceId"]: r for r in _flagged(ds, "Idle Load Balancers")}
    by_arn: dict[str, Decimal] = {}
    for ln in ds.current():
        if ln.service != "AWSELB":
            continue
        tail = ln.resource.split(":loadbalancer/", 1)[1]
        name = tail.split("/")[1] if tail.startswith("app/") else tail
        if name in names:
            by_arn[name] = by_arn.get(name, Decimal(0)) + ln.cost
    for name, r in names.items():
        f.details.append(
            Detail(r["accountId"], name, f"{r['metadata']['type']}, 0 requests in 14 days", by_arn[name], Decimal(0))
        )
    return f


def idle_instance_volumes(ds: Dataset) -> set[str]:
    out: set[str] = set()
    if ds.assumptions["idle"]["delete_volumes_of_idle_instances"]:
        for r in _flagged(ds, "Low Utilization Amazon EC2 Instances"):
            out.update(r["metadata"]["attachedVolumes"])
    return out


def idle_instances(ds: Dataset) -> Finding:
    costs = ds.cost_by_resource()
    f = Finding(
        "idle-instances",
        "Stop, then terminate idle untagged instances",
        "idle",
        basis="Instance hours plus attached volumes billed in the analysis period.",
    )
    volumes = idle_instance_volumes(ds)
    for r in _flagged(ds, "Low Utilization Amazon EC2 Instances"):
        meta = r["metadata"]
        f.details.append(
            Detail(
                r["accountId"],
                r["resourceId"],
                f"{meta['instanceName']} ({meta['instanceType']}), {meta['fourteenDayAverageCpuPercent']}% average CPU",
                costs[r["resourceId"]],
                Decimal(0),
            )
        )
        for vol in (v for v in meta["attachedVolumes"] if v in volumes):
            f.details.append(
                Detail(r["accountId"], vol, f"root volume of {meta['instanceName']}", costs[vol], Decimal(0))
            )
    return f


def old_snapshots(ds: Dataset) -> Finding:
    cfg = ds.assumptions["idle"]
    threshold = cfg["snapshot_age_threshold_days"]
    in_ami = {s for img in ds.images for s in img["SnapshotIds"]}
    f = Finding(
        "old-snapshots",
        f"Delete EBS snapshots older than {threshold} days",
        "idle",
        basis="Snapshot storage billed in the analysis period for snapshots past the age threshold, "
        "not referenced by an AMI and without a retention tag.",
    )
    for s in ds.snapshots:
        keys = {t["Key"] for t in s["Tags"]}
        if s["AgeDays"] <= threshold or s["SnapshotId"] in in_ami or cfg["snapshot_retention_tag_key"] in keys:
            continue
        line = ds.usage_line(f":snapshot/{s['SnapshotId']}", "EBS:SnapshotUsage")
        f.details.append(
            Detail(
                s["OwnerId"],
                s["SnapshotId"],
                f"{s['BilledSizeGiB']:,} GiB billed, {s['AgeDays']} days old",
                line.cost,
                Decimal(0),
            )
        )
    return f


# --- Rightsizing -----------------------------------------------------------------
def _box_lines(ds: Dataset) -> dict[str, list]:
    out: dict[str, list] = {}
    for ln in ds.current():
        if ln.usage_type.startswith("BoxUsage:"):
            out.setdefault(ln.resource, []).append(ln)
    return out


def rightsize_ec2(ds: Dataset) -> Finding:
    box = _box_lines(ds)
    f = Finding(
        "rightsize-ec2",
        "Rightsize over-provisioned EC2 instances",
        "rightsizing",
        basis="Current instance-hour cost from the CUR; target is the same hours at the "
        "Compute Optimizer rank-1 instance type's on-demand rate.",
    )
    for rec in ds.ec2_recs:
        if rec["finding"] != "Overprovisioned":
            continue
        option = next(o for o in rec["recommendationOptions"] if o["rank"] == 1)
        iid = rec["instanceArn"].rsplit("/", 1)[1]
        lines = [ln for ln in box.get(iid, []) if ln.line_type == "Usage"]
        if not lines:
            continue  # not running in the analysis period, or already covered
        hours = sum((ln.usage for ln in lines), Decimal(0))
        current = sum((ln.cost for ln in lines), Decimal(0))
        target = hours * ds.price("ec2_hourly", option["instanceType"])
        cpu = next(m["value"] for m in rec["utilizationMetrics"] if m["name"] == "CPU")
        mem = next(m["value"] for m in rec["utilizationMetrics"] if m["name"] == "MEMORY")
        f.details.append(
            Detail(
                rec["accountId"],
                iid,
                f"{rec['instanceName']}: {rec['currentInstanceType']} to {option['instanceType']} "
                f"(max CPU {cpu:g}%, max memory {mem:g}%)",
                current,
                target,
            )
        )
    return f


def aurora_instances(ds: Dataset, arn: str) -> int:
    """Instances in an Aurora cluster: its instance-hours in the analysis period over the hours in a month."""
    hours = sum(
        (ln.usage for ln in ds.current() if ln.resource == arn and ln.usage_type.startswith("InstanceUsage:")),
        Decimal(0),
    )
    count = hours / ds.hours
    if count != count.to_integral_value() or count < 1:
        raise ValueError(f"{arn}: {hours} instance-hours is not a whole number of instances")
    return int(count)


def aurora_target_instances(ds: Dataset, cluster_id: str, arn: str) -> int:
    """Instances after the change: the current count unless data/assumptions.json removes readers."""
    targets = {k: v for k, v in ds.assumptions["aurora_target_instances"].items() if not k.startswith("_")}
    return int(targets[cluster_id]) if cluster_id in targets else aurora_instances(ds, arn)


def rds_cluster_arn(rec: dict) -> str:
    """The Aurora cluster ARN for a Compute Optimizer RDS recommendation.

    Compute Optimizer returns one recommendation per DB instance, so resourceArn names a
    writer or reader instance; cluster membership comes only from dbClusterIdentifier.
    """
    region = rec["resourceArn"].split(":")[3]
    return f"arn:aws:rds:{region}:{rec['accountId']}:cluster:{rec['dbClusterIdentifier']}"


def _rank1_class(rec: dict) -> str | None:
    return next((o["dbInstanceClass"] for o in rec["instanceRecommendationOptions"] if o["rank"] == 1), None)


def rds_clusters(ds: Dataset) -> list[tuple[str, dict]]:
    """(cluster ARN, recommendation) once per Aurora cluster, from the per-instance recommendations.

    The audit resizes every instance of a cluster to one class, so all instances of a cluster
    must agree on the finding and the rank-1 class; a disagreement raises instead of guessing.
    """
    clusters: dict[str, dict] = {}
    for rec in ds.rds_recs:
        if "dbClusterIdentifier" not in rec:
            raise ValueError(f"{rec['resourceArn']}: not an Aurora cluster member")
        arn = rds_cluster_arn(rec)
        first = clusters.setdefault(arn, rec)
        fields = ("instanceFinding", "currentDBInstanceClass")
        if [first[k] for k in fields] + [_rank1_class(first)] != [rec[k] for k in fields] + [_rank1_class(rec)]:
            raise ValueError(f"{arn}: instances {first['resourceArn']} and {rec['resourceArn']} disagree")
    return list(clusters.items())


def rds_target_cost(ds: Dataset, cls: str, instances: int) -> Decimal:
    """Monthly on-demand instance cost of an Aurora cluster: a writer plus any readers of one class."""
    return ds.hours * ds.price("aurora_postgresql_hourly", cls) * instances


def aurora_layout(instances: int) -> str:
    if instances == 1:
        return "writer only"
    return "writer and reader" if instances == 2 else f"writer and {instances - 1} readers"


def rightsize_rds(ds: Dataset, environment: str) -> Finding:
    instance_cost: dict[str, Decimal] = {}
    for ln in ds.current():
        if ln.service == "AmazonRDS" and ln.usage_type.startswith("InstanceUsage:"):
            instance_cost[ln.resource] = instance_cost.get(ln.resource, Decimal(0)) + ln.cost
    env_of = {ln.resource: ln.tag("environment") for ln in ds.current() if ln.service == "AmazonRDS"}
    title = {
        "prod": "Rightsize the production orders database",
        "staging": "Rightsize the staging orders database and remove its reader",
    }[environment]
    f = Finding(
        f"rightsize-rds-{environment}",
        title,
        "rightsizing",
        basis="Current instance-hour cost from the CUR; target uses the Compute Optimizer rank-1 class at "
        "on-demand rates, for the instance count in data/assumptions.json. "
        "Aurora storage and I/O do not change with the instance class.",
    )
    for arn, rec in rds_clusters(ds):
        if rec["instanceFinding"] != "Overprovisioned" or env_of.get(arn) != environment:
            continue
        option = next(o for o in rec["instanceRecommendationOptions"] if o["rank"] == 1)
        name = rec["dbClusterIdentifier"]
        now, after = aurora_instances(ds, arn), aurora_target_instances(ds, name, arn)
        target = rds_target_cost(ds, option["dbInstanceClass"], after)
        f.details.append(
            Detail(
                rec["accountId"],
                name,
                f"{rec['currentDBInstanceClass']} {aurora_layout(now)} to "
                f"{option['dbInstanceClass']} {aurora_layout(after)}",
                instance_cost[arn],
                target,
            )
        )
    return f


# --- Usage and storage changes ------------------------------------------------------
def scheduled_hours(ds: Dataset) -> Decimal:
    s = ds.assumptions["staging_schedule"]
    return D(s["hours_per_day"]) * D(s["days_per_week"]) * D(s["weeks_per_year"]) / 12


def schedule_staging(ds: Dataset) -> Finding:
    cfg = ds.assumptions["staging_schedule"]
    hours_on = scheduled_hours(ds)
    f = Finding(
        "schedule-staging",
        "Run staging order-api instances on a working-hours schedule",
        "usage",
        basis=f"Instance cost scaled from {ds.hours} to {hours_on} running hours a month.",
    )
    for iid, lines in _box_lines(ds).items():
        usage = [ln for ln in lines if ln.line_type == "Usage"]
        if not usage:
            continue  # covered by a Savings Plan; scheduling it would strand the commitment
        ln = usage[0]
        if ln.tag("environment") != cfg["environment"] or ln.tag("application") not in cfg["applications"]:
            continue
        hours = sum((x.usage for x in usage), Decimal(0))
        cost = sum((x.cost for x in usage), Decimal(0))
        target = cost / hours * min(hours, hours_on)
        f.details.append(Detail(ln.account, iid, f"{ln.tag('Name')} ({ln.instance_type})", cost, target))
    return f


def gp2_to_gp3(ds: Dataset) -> Finding:
    unattached = {r["resourceId"] for r in _flagged(ds, "Underutilized Amazon EBS Volumes")}
    excluded = unattached | idle_instance_volumes(ds)
    cfg = ds.assumptions["gp3_migration"]
    gp3 = ds.price("ebs_gb_month", "gp3")
    extra_mibps = D(cfg["gp2_max_throughput_mibps"]) - D(cfg["included_throughput_mibps"])
    throughput = extra_mibps * ds.price("gp3_throughput_mibps_month")
    f = Finding(
        "gp2-to-gp3",
        "Change attached gp2 volumes to gp3",
        "usage",
        basis="gp2 GB-months in the analysis period repriced at gp3, plus provisioned throughput on volumes "
        f"over {cfg['match_gp2_throughput_above_gib']} GiB so they keep gp2's {cfg['gp2_max_throughput_mibps']} "
        f"MiB/s. Volumes over {cfg['max_size_gib']:,} GiB are left out: they would also need provisioned IOPS. "
        "Every volume ran the full month, so GB-months equal the volume size.",
    )
    for ln in ds.current():
        if ln.usage_type != "EBS:VolumeUsage.gp2" or ln.resource in excluded or ln.usage > cfg["max_size_gib"]:
            continue
        needs_throughput = ln.usage > cfg["match_gp2_throughput_above_gib"]
        target = ln.usage * gp3 + (throughput if needs_throughput else Decimal(0))
        note = f", +{extra_mibps} MiB/s" if needs_throughput else ""
        f.details.append(
            Detail(ln.account, ln.resource, f"{ln.usage:,} GiB ({ln.tag('Name') or 'untagged'}){note}", ln.cost, target)
        )
    return f


def log_retention(ds: Dataset) -> Finding:
    cfg = ds.assumptions["cloudwatch_logs"]
    ratio = D(cfg["stored_to_ingested_ratio"])
    price = ds.price("cloudwatch_logs_storage_gb_month")
    f = Finding(
        "log-retention",
        "Set CloudWatch Logs retention on groups that never expire",
        "usage",
        basis="Steady-state stored GB = monthly ingest x stored-to-ingested ratio x retention months; "
        "the saving is the stored GB above that, at the storage rate.",
    )
    for g in ds.log_groups:
        target_days = cfg["retention_days_by_class"][g["class"]]
        if g["retentionInDays"] is not None and g["retentionInDays"] <= target_days:
            continue
        line = ds.usage_line(f":log-group:{g['logGroupName']}", "TimedStorage-ByteHrs")
        stored = line.usage
        retained = min(stored, D(g["monthlyIngestGB"]) * ratio * D(target_days) / 30)
        now = "never expires" if g["retentionInDays"] is None else f"{g['retentionInDays']} days"
        f.details.append(
            Detail(
                g["accountId"],
                g["logGroupName"],
                f"{g['class']}, {now} to {target_days} days, {stored:,.0f} GB stored to {retained:,.0f} GB",
                line.cost,
                retained * price,
            )
        )
    return f


def debug_logging(ds: Dataset) -> Finding:
    cfg = ds.assumptions["cloudwatch_logs"]
    share = D(cfg["debug_share_of_order_api_ingest"])
    price = ds.price("cloudwatch_logs_ingest_per_gb")
    g = next(x for x in ds.log_groups if x["logGroupName"] == cfg["debug_log_group"])
    line = ds.usage_line(f":log-group:{g['logGroupName']}", "DataProcessing-Bytes")
    ingest = line.usage
    f = Finding(
        "debug-logging",
        "Turn off DEBUG logging in production order-api",
        "usage",
        basis="Ingested GB x assumed DEBUG share x ingestion rate. The storage effect is ignored, "
        "which keeps the estimate conservative.",
    )
    f.details.append(
        Detail(
            g["accountId"],
            g["logGroupName"],
            f"{ingest:,.0f} GB a month ingested, {pct(share, 0)} assumed DEBUG",
            line.cost,
            ingest * (1 - share) * price,
        )
    )
    return f


def s3_lifecycle(ds: Dataset) -> Finding:
    cfg = ds.assumptions["s3_lifecycle"]
    after = cfg["transition_after_days"]
    std = ds.price("s3_gb_month", "STANDARD")
    target = ds.price("s3_gb_month", cfg["target_storage_class"])
    f = Finding(
        "s3-lifecycle",
        f"Move application logs older than {after} days to S3 Glacier Instant Retrieval",
        "usage",
        basis="GB older than the transition age repriced at the target class, minus expected retrieval fees "
        "and the monthly transition requests for objects that reach the transition age; moving the existing "
        "backlog is a one-time cost.",
    )
    gb = objects = monthly_objects = Decimal(0)
    for band in ds.s3_age:
        if band["bucket"] != cfg["bucket"]:
            continue
        low = int(band["age_band_days"].rstrip("+").split("-")[0])
        if low > after:
            gb += D(band["size_gb"])
            objects += D(band["object_count"])
        elif low == 0:
            # The youngest band holds `high` days of new objects; about 30 days' worth reach the rule each month.
            high = int(band["age_band_days"].split("-")[1])
            monthly_objects += D(band["object_count"]) * 30 / high
    f.details.append(
        Detail(
            _bucket_account(ds, cfg["bucket"]),
            cfg["bucket"],
            f"{gb:,} GB in {objects:,} objects older than {after} days",
            gb * std,
            gb * target,
        )
    )
    reads = D(cfg["expected_retrieval_gb_per_month"])
    transitions = monthly_objects / 1000 * ds.price("s3_lifecycle_transition_per_1000_objects")
    f.adjustment = -(reads * ds.price("s3_glacier_ir_retrieval_per_gb") + transitions)
    f.adjustment_note = (
        f"retrieval fees for {reads} GB of reads and transition requests for {monthly_objects:,} new objects a month"
    )
    f.one_time = to_cents(objects / 1000 * ds.price("s3_lifecycle_transition_per_1000_objects"))
    return f


def _bucket_account(ds: Dataset, bucket: str) -> str:
    return next(ln.account for ln in ds.current() if ln.resource == bucket)


def nat_consolidation(ds: Dataset) -> Finding:
    cfg = ds.assumptions["nat_consolidation"]
    gws = [g for g in ds.nat_gateways if g["Environment"] == cfg["environment"]]
    remove = sorted(g["NatGatewayId"] for g in gws)[cfg["keep_gateways"] :]
    f = Finding(
        "nat-consolidation",
        "Consolidate staging NAT gateways to one",
        "usage",
        basis="Hourly charge of the removed gateways; their traffic moves to the remaining gateway and "
        "adds cross-AZ transfer at the inter-AZ rate.",
    )
    extra_gb = Decimal(0)
    for ln in ds.current():
        nid = ln.resource.rsplit("/", 1)[-1]
        if nid not in remove:
            continue
        if ln.usage_type == "NatGateway-Hours":
            f.details.append(Detail(ln.account, nid, f"{ln.tag('Name')} hourly charge", ln.cost, Decimal(0)))
        elif ln.usage_type == "NatGateway-Bytes":
            extra_gb += ln.usage
    f.adjustment = -extra_gb * ds.price("inter_az_transfer_per_gb")
    f.adjustment_note = f"cross-AZ transfer for {extra_gb} GB moved to the remaining gateway"
    return f


def floor_to(value: Decimal, increment: Decimal) -> Decimal:
    return (value / increment).to_integral_value(rounding=ROUND_FLOOR) * increment


def all_findings(ds: Dataset) -> list[Finding]:
    """Non-commitment findings, in a stable order. Commitments are sized after these."""
    return [
        rightsize_ec2(ds),
        rightsize_rds(ds, "prod"),
        rightsize_rds(ds, "staging"),
        schedule_staging(ds),
        unattached_volumes(ds),
        gp2_to_gp3(ds),
        old_snapshots(ds),
        idle_eips(ds),
        idle_load_balancers(ds),
        idle_instances(ds),
        log_retention(ds),
        debug_logging(ds),
        s3_lifecycle(ds),
        nat_consolidation(ds),
    ]
