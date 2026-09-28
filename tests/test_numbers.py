"""Every savings figure, recomputed by hand from the raw data and unit prices.

The expected values are written as the arithmetic a reviewer would do on paper
(hours x rate, GB x price), not copied from the scripts' output. If the data,
an assumption or the code changes, these tests show which figure moved.
"""

import csv
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal

import pytest
from costaudit.model import ROOT

H = Decimal(730)


def d(x: str) -> Decimal:
    return Decimal(x)


def money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


def raw_totals() -> dict[str, Decimal]:
    """Period totals straight from the CSV, without the costaudit loader."""
    out: dict[str, Decimal] = defaultdict(Decimal)
    with (ROOT / "data/synthetic/cur/cost-and-usage.csv").open() as fh:
        for r in csv.DictReader(fh):
            out[r["bill_billing_period"]] += Decimal(r["line_item_unblended_cost"])
    return out


def test_period_totals():
    t = raw_totals()
    assert money(t["M1"]) == d("22308.74")
    assert money(t["M2"]) == d("24080.22")
    assert money(t["M3"]) == d("24502.82")


def test_loader_agrees_with_raw_csv(ds):
    from costaudit import analysis

    assert analysis.totals(ds) == raw_totals()


EXPECTED = {
    # Six app instances, m5.2xlarge to m5.xlarge, full month.
    "rightsize-ec2": 6 * (d("0.384") - d("0.192")) * H,
    # orders-db (Aurora PostgreSQL): writer and reader, db.r5.4xlarge to db.r5.2xlarge; storage and I/O unchanged.
    "rightsize-rds-prod": (d("2.32") - d("1.16")) * 2 * H,
    # orders-db-stg: writer and reader on db.r5.2xlarge to one db.r5.large writer; storage and I/O unchanged.
    "rightsize-rds-staging": (d("1.16") * 2 - d("0.29")) * H,
    # Four staging instances at 0.384/h, from 730 to 12 x 5 x 52 / 12 = 260 hours.
    "schedule-staging": 4 * d("0.384") * (H - 12 * 5 * 52 / Decimal(12)),
    # gp2 1,000 + 500 + 500 + 250 GB at 0.10, gp3 2,000 GB at 0.08.
    "unattached-ebs": (1000 + 500 + 500 + 250) * d("0.10") + 2000 * d("0.08"),
    # 18 attached gp2 volumes: 4 x 100 + 6 x 500 + 4 x 500 + 500 + 3 x 100 GB, 0.02 cheaper on gp3.
    # The eleven 500 GB volumes also buy 125 MiB/s of extra gp3 throughput at 0.04 to keep gp2's 250 MiB/s.
    "gp2-to-gp3": (400 + 3000 + 2000 + 500 + 300) * (d("0.10") - d("0.08")) - 11 * 125 * d("0.04"),
    # Snapshots older than 180 days, not in an AMI, no retention tag: 900 + 650 + 400 + 500 GB.
    "old-snapshots": (900 + 650 + 400 + 500) * d("0.05"),
    # Four idle addresses, 730 hours at 0.005.
    "idle-eip": 4 * H * d("0.005"),
    # One ALB (0.0225/h, zero LCU) and one Classic Load Balancer (0.025/h).
    "idle-load-balancers": H * (d("0.0225") + d("0.025")),
    # Two t3.large plus their 100 GB gp2 root volumes.
    "idle-instances": 2 * (H * d("0.0832") + 100 * d("0.10")),
    # Stored GB above ingest x 0.30 x retention months, at 0.03 per GB-month.
    "log-retention": d("0.03")
    * ((9000 - 1200 * d("0.3")) + (3600 - 300 * d("0.3")) + (4800 - 400 * d("0.3") * 6) + (1800 - 150 * d("0.3"))),
    # 60% of 1,200 GB ingested at 0.50 per GB.
    "debug-logging": 1200 * d("0.6") * d("0.50"),
    # 20,000 GB older than 30 days from 0.023 to 0.004, less 50 GB of retrievals at 0.03 and the
    # 4,000,000 objects a month that reach 30 days, transitioned at 0.02 per 1,000.
    "s3-lifecycle": 20000 * (d("0.023") - d("0.004")) - 50 * d("0.03") - 4_000_000 / Decimal(1000) * d("0.02"),
    # Two of three staging NAT gateways, less 40 GB moved cross-AZ at 0.02.
    "nat-consolidation": 2 * H * d("0.045") - 40 * d("0.02"),
    # Production after resize: orders-db writer and reader at 2 x 1.16/h, reporting-db at 0.58/h, 30% discount.
    "rds-reserved-instances": (d("1.16") * 2 + d("0.58")) * H * d("0.30"),
}


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_monthly_saving(audit, key):
    assert audit.by_key(key).finding.monthly == money(EXPECTED[key])


def test_compute_savings_plan_sizing(audit):
    discount = 1 - d("408.80") / d("560.64")  # observed on the existing plan
    baseline = 4 * d("0.192") + 4 * d("0.68") + d("0.0416") + 2 * d("0.17") + 3 * d("0.0832")
    commitment = (baseline * d("0.80") * (1 - discount) / d("0.001")).to_integral_value(ROUND_FLOOR) * d("0.001")
    saving = (commitment / (1 - discount) - commitment) * H
    assert audit.sizing.baseline_hourly_od == baseline == d("4.1192")
    assert audit.sizing.commitment_hourly == commitment == d("2.402")
    assert audit.by_key("compute-savings-plan").finding.monthly == money(saving)


def test_one_time_costs(audit):
    assert audit.by_key("unattached-ebs").finding.one_time == (1000 + 500 + 500 + 2000 + 250) * d("0.05")
    assert audit.by_key("s3-lifecycle").finding.one_time == 40_000_000 / Decimal(1000) * d("0.02")


def test_coverage(audit):
    c = audit.coverage
    eligible = (
        d("560.64")
        + (6 * d("0.384") + 4 * d("0.68") + d("0.0416") + 4 * d("0.384") + d("0.34") + 2 * d("0.17") + 5 * d("0.0832"))
        * H
        + d("140")  # Lambda in M3 (flat cost line; Lambda is Compute Savings Plan eligible)
        + d("354.60")
        + d("77.88")  # storefront Fargate vCPU and GB hours (12 tasks x 1 vCPU, 2 GB x 730 h)
    )
    assert c.eligible_od == eligible
    assert c.sp_coverage == d("560.64") / eligible
    assert c.rds_coverage == 0


def test_tag_coverage(ds):
    from costaudit import analysis

    by_tag = {t.tag: t for t in analysis.tag_coverage(ds)}
    # Untagged by application: untagged resources, data transfer and the Savings Plan fee.
    assert money(by_tag["application"].untagged) == d("2494.25")
    # environment also misses the two ElastiCache nodes (2 x 730 x 0.216).
    assert by_tag["environment"].untagged - by_tag["application"].untagged == 2 * H * d("0.216")
    # cost-center also misses CloudFront (30,000 GB x 0.085) and the ElastiCache nodes are tagged.
    assert by_tag["cost-center"].untagged - by_tag["application"].untagged == 30000 * d("0.085")


def test_keeping_idle_instance_volumes_moves_them_to_gp3(ds):
    """With the volume flag off, the root volumes are neither deleted nor counted twice."""
    from copy import deepcopy

    from costaudit import analysis

    kept = deepcopy(ds)
    kept.assumptions["idle"]["delete_volumes_of_idle_instances"] = False
    audit = analysis.run(kept)
    idle = audit.by_key("idle-instances").finding
    gp3 = audit.by_key("gp2-to-gp3").finding
    assert idle.monthly == money(2 * H * d("0.0832"))
    assert not set(idle.resources) & set(gp3.resources)
    assert gp3.monthly == money(EXPECTED["gp2-to-gp3"] + 2 * 100 * (d("0.10") - d("0.08")))


def test_aurora_layout_comes_from_the_cur(ds):
    from costaudit import findings

    arn = "arn:aws:rds:us-east-1:{}:cluster:{}"
    assert findings.aurora_instances(ds, arn.format("111122223333", "orders-db")) == 2
    assert findings.aurora_instances(ds, arn.format("111122223333", "reporting-db")) == 1
    assert findings.aurora_target_instances(ds, arn.format("444455556666", "orders-db-stg")) == 1
    assert all("multiAZ" not in rec for rec in ds.rds_recs)
