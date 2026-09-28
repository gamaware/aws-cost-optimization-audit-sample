#!/usr/bin/env python3
"""Generate the synthetic Harbor Goods billing and inventory exports.

Harbor Goods is a fictional retailer. Every account ID is an AWS documentation
example ID and every resource ID is made up. The output is deterministic: the
same code always writes byte-identical files, and a test checks that the
committed files match.

Billing periods are labelled M1, M2 and M3 (oldest to newest) instead of
calendar months so the sample stays dateless.

Usage: python scripts/generate_synthetic.py [--out data/synthetic] [--check]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PERIODS = ("M1", "M2", "M3")
HOURS = Decimal(730)
REGION = "us-east-1"

PROD = "111122223333"
STAGING = "444455556666"
SHARED = "123456789012"

# Billed on-demand rates (USD). They approximate us-east-1 Linux list prices.
RATE = {
    "ec2": {
        "m5.xlarge": "0.192",
        "m5.2xlarge": "0.384",
        "c5.xlarge": "0.17",
        "c5.2xlarge": "0.34",
        "c5.4xlarge": "0.68",
        "t3.medium": "0.0416",
        "t3.large": "0.0832",
    },
    "rds": {"db.r5.xlarge": "0.58", "db.r5.2xlarge": "1.16", "db.r5.4xlarge": "2.32"},  # Aurora PostgreSQL
    "ebs": {"gp2": "0.10", "gp3": "0.08", "snapshot": "0.05"},
    "aurora_storage": "0.10",
    "aurora_io": "0.0000002",  # per I/O request (0.20 per million)
    "cache.r5.large": "0.216",
    "redshift.ra3.xlplus": "1.086",
    "alb_hour": "0.0225",
    "clb_hour": "0.025",
    "lcu": "0.008",
    "nat_hour": "0.045",
    "nat_gb": "0.045",
    "idle_ipv4_hour": "0.005",
    "s3_standard": "0.023",
    "logs_ingest": "0.50",
    "logs_storage": "0.03",
    "transfer_out": "0.09",
    "cloudfront_out": "0.085",
}

COLUMNS = [
    "bill_billing_period",
    "line_item_usage_account_id",
    "line_item_line_item_type",
    "product_servicecode",
    "line_item_resource_id",
    "line_item_usage_type",
    "line_item_operation",
    "product_instance_type",
    "product_region_code",
    "pricing_term",
    "line_item_usage_amount",
    "pricing_public_on_demand_cost",
    "line_item_unblended_cost",
    "resource_tags_user_name",
    "resource_tags_user_application",
    "resource_tags_user_environment",
    "resource_tags_user_cost_center",
]

SP_ARN = f"arn:aws:savingsplans::{PROD}:savingsplan/0a0b0c0d-0000-4000-8000-000000000001"
SP_COMMITMENT = Decimal("0.56")


def d(value: str | int | Decimal) -> Decimal:
    return Decimal(str(value))


def cents(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def tags(name: str = "", app: str = "", env: str = "", cc: str = "") -> dict[str, str]:
    return {
        "resource_tags_user_name": name,
        "resource_tags_user_application": app,
        "resource_tags_user_environment": env,
        "resource_tags_user_cost_center": cc,
    }


# --- Resource catalog -------------------------------------------------------
# Each instance: (name, id, account, type, tags, periods present, covered by SP)
def instances() -> list[dict]:
    out = []

    def add(name, iid, acct, itype, tag, periods=PERIODS, sp=False):
        out.append({"name": name, "id": iid, "account": acct, "type": itype, "tags": tag, "periods": periods, "sp": sp})

    for n in range(1, 5):
        add(
            f"report-0{n}",
            f"i-0a10000000000000{n}",
            PROD,
            "m5.xlarge",
            tags(f"report-0{n}", "reporting", "prod", "finance"),
            sp=True,
        )
    for n in range(1, 7):
        present = PERIODS if n <= 4 else ("M2", "M3")
        add(
            f"app-0{n}",
            f"i-0a20000000000000{n}",
            PROD,
            "m5.2xlarge",
            tags(f"app-0{n}", "order-api", "prod", "digital"),
            present,
        )
    for n in range(1, 5):
        add(
            f"batch-0{n}",
            f"i-0a30000000000000{n}",
            PROD,
            "c5.4xlarge",
            tags(f"batch-0{n}", "inventory-sync", "prod", "supply-chain"),
        )
    add("bastion-01", "i-0a400000000000001", PROD, "t3.medium", tags("bastion-01", "platform", "prod", "platform"))
    for n in range(1, 5):
        present = PERIODS if n <= 2 else ("M2", "M3")
        add(
            f"stg-app-0{n}",
            f"i-0b10000000000000{n}",
            STAGING,
            "m5.2xlarge",
            tags(f"stg-app-0{n}", "order-api", "staging", "digital"),
            present,
        )
    add("stg-batch-01", "i-0b200000000000001", STAGING, "c5.2xlarge", tags())
    for n in range(1, 3):
        add(
            f"ci-runner-0{n}",
            f"i-0c10000000000000{n}",
            SHARED,
            "c5.xlarge",
            tags(f"ci-runner-0{n}", "ci", "shared", "platform"),
        )
    for n in range(1, 6):
        tag = tags(f"dev-0{n}", "sandbox", "dev", "digital") if n <= 3 else tags(f"dev-0{n}")
        add(f"dev-0{n}", f"i-0c20000000000000{n}", SHARED, "t3.large", tag)
    return out


# Attached volumes follow their instance. (instance name, volume id, type, GB)
ATTACHED_VOLUMES = (
    [(f"report-0{n}", f"vol-0a10000000000000{n}", "gp2", 100) for n in range(1, 5)]
    + [(f"app-0{n}", f"vol-0a20000000000000{n}", "gp2", 500) for n in range(1, 7)]
    + [(f"batch-0{n}", f"vol-0a30000000000000{n}", "gp3", 1000) for n in range(1, 5)]
    + [("bastion-01", "vol-0a400000000000001", "gp3", 30)]
    + [(f"stg-app-0{n}", f"vol-0b10000000000000{n}", "gp2", 500) for n in range(1, 5)]
    + [("stg-batch-01", "vol-0b200000000000001", "gp2", 500)]
    + [(f"ci-runner-0{n}", f"vol-0c10000000000000{n}", "gp3", 200) for n in range(1, 3)]
    + [(f"dev-0{n}", f"vol-0c20000000000000{n}", "gp2", 100) for n in range(1, 6)]
)

# Unattached volumes: (id, account, type, GB, periods, former owner note)
UNATTACHED_VOLUMES = [
    ("vol-0a9000000000000e1", PROD, "gp2", 1000, PERIODS, "left over from the app fleet rebuild"),
    ("vol-0a9000000000000e2", PROD, "gp2", 500, PERIODS, "detached test restore"),
    ("vol-0b9000000000000e1", STAGING, "gp2", 500, PERIODS, "old staging database volume"),
    ("vol-0c9000000000000e1", SHARED, "gp3", 2000, PERIODS, "retired build cache"),
    ("vol-0c9000000000000e2", SHARED, "gp2", 250, ("M2", "M3"), "detached from a terminated dev box"),
]

# Snapshots: (id, account, source volume, billed GB, age in days at M3, retention tag)
SNAPSHOTS = [
    ("snap-0a1000000000000001", PROD, "vol-0a200000000000001", 120, 12, ""),
    ("snap-0a1000000000000002", PROD, "vol-0a200000000000001", 80, 40, ""),
    ("snap-0a1000000000000003", PROD, "vol-0a100000000000001", 60, 200, ""),
    ("snap-0a1000000000000004", PROD, "vol-0a9000000000000e1", 900, 420, ""),
    ("snap-0a1000000000000005", PROD, "vol-0a300000000000001", 700, 380, "legal-hold"),
    ("snap-0a1000000000000006", PROD, "vol-0a300000000000002", 650, 610, ""),
    ("snap-0b1000000000000001", STAGING, "vol-0b9000000000000e1", 400, 300, ""),
    ("snap-0b1000000000000002", STAGING, "vol-0b100000000000001", 150, 30, ""),
    ("snap-0c1000000000000001", SHARED, "vol-0c9000000000000e1", 500, 250, ""),
    ("snap-0c1000000000000002", SHARED, "vol-0c100000000000001", 90, 190, ""),
]
# Snapshots that back a registered AMI (cannot be deleted while the AMI exists).
AMIS = [
    {
        "ImageId": "ami-0a1000000000000001",
        "Name": "harbor-goods-reporting-golden",
        "OwnerId": PROD,
        "SnapshotIds": ["snap-0a1000000000000003"],
    },
    {
        "ImageId": "ami-0c1000000000000001",
        "Name": "harbor-goods-ci-runner",
        "OwnerId": SHARED,
        "SnapshotIds": ["snap-0c1000000000000002"],
    },
]

IDLE_EIPS = [
    ("eipalloc-0a1000000000000001", PROD, "203.0.113.10"),
    ("eipalloc-0a1000000000000002", PROD, "203.0.113.11"),
    ("eipalloc-0b1000000000000001", STAGING, "203.0.113.20"),
    ("eipalloc-0c1000000000000001", SHARED, "203.0.113.30"),
]

# Load balancers: (name, account, kind, monthly LCU by period, requests over 14 days, tags)
LOAD_BALANCERS = [
    (
        "storefront-alb",
        PROD,
        "application",
        (2000, 2100, 2200),
        41_000_000,
        tags("storefront-alb", "storefront", "prod", "digital"),
    ),
    (
        "order-api-alb",
        PROD,
        "application",
        (1100, 1400, 1500),
        18_500_000,
        tags("order-api-alb", "order-api", "prod", "digital"),
    ),
    ("legacy-promo-alb", PROD, "application", (0, 0, 0), 0, tags()),
    (
        "order-api-stg-alb",
        STAGING,
        "application",
        (40, 40, 40),
        220_000,
        tags("order-api-stg-alb", "order-api", "staging", "digital"),
    ),
    ("stg-legacy-clb", STAGING, "classic", (0, 0, 0), 0, tags()),
]

# NAT gateways: (id, account, AZ, GB processed by period, tags)
NAT_GATEWAYS = [
    *[
        (
            f"nat-0a100000000000000{n}",
            PROD,
            f"us-east-1{az}",
            (2600, 2800, 3000),
            tags(f"prod-nat-{az}", "network", "prod", "platform"),
        )
        for n, az in ((1, "a"), (2, "b"), (3, "c"))
    ],
    *[
        (
            f"nat-0b100000000000000{n}",
            STAGING,
            f"us-east-1{az}",
            (20, 20, 20),
            tags(f"stg-nat-{az}", "network", "staging", "platform"),
        )
        for n, az in ((1, "a"), (2, "b"), (3, "c"))
    ],
]

# Aurora PostgreSQL clusters: (id, account, class, multi_az, storage GB, million I/O requests, tags).
# Multi-AZ means a writer plus one reader of the same class in a second Availability Zone; storage is billed once.
RDS = [
    ("orders-db", PROD, "db.r5.4xlarge", True, 1000, 2000, tags("orders-db", "order-api", "prod", "digital")),
    ("reporting-db", PROD, "db.r5.xlarge", False, 500, 300, tags("reporting-db", "reporting", "prod", "finance")),
    (
        "orders-db-stg",
        STAGING,
        "db.r5.2xlarge",
        True,
        500,
        100,
        tags("orders-db-stg", "order-api", "staging", "digital"),
    ),
]

# CloudWatch Logs groups: (name, account, class, retention days or None, ingest GB by period, stored GB by period, tags)
LOG_GROUPS = [
    (
        "/harbor-goods/order-api",
        PROD,
        "application",
        None,
        (900, 1050, 1200),
        (6300, 7650, 9000),
        tags("", "order-api", "prod", "digital"),
    ),
    (
        "/harbor-goods/storefront",
        PROD,
        "application",
        None,
        (300, 300, 300),
        (3000, 3300, 3600),
        tags("", "storefront", "prod", "digital"),
    ),
    (
        "/aws/lambda/image-resizer",
        PROD,
        "application",
        30,
        (40, 40, 40),
        (200, 200, 200),
        tags("", "image-resizer", "prod", "digital"),
    ),
    (
        "/harbor-goods/vpc-flow",
        PROD,
        "network",
        None,
        (400, 400, 400),
        (4000, 4400, 4800),
        tags("", "network", "prod", "platform"),
    ),
    ("/harbor-goods/order-api-stg", STAGING, "application", None, (150, 150, 150), (1500, 1650, 1800), tags()),
]

# S3 buckets: (name, account, Standard GB by period, tags)
BUCKETS = [
    ("harbor-goods-app-logs", SHARED, (18000, 20000, 22000), tags("", "logging", "shared", "platform")),
    ("harbor-goods-product-images", PROD, (3000, 3000, 3000), tags("", "storefront", "prod", "digital")),
    ("harbor-goods-data-lake", PROD, (40000, 40000, 40000), tags("", "analytics", "prod", "finance")),
]
# Age profile of harbor-goods-app-logs at M3: (age band, GB, objects)
LOG_BUCKET_AGE = [
    ("0-30", 2000, 4_000_000),
    ("31-90", 4000, 8_000_000),
    ("91-365", 12000, 24_000_000),
    ("366+", 4000, 8_000_000),
]

# Flat-cost services: (service, account, resource, usage type, operation, cost by period, eligible for Compute SP, tags)
# The storefront web tier runs on ECS Fargate: 12 tasks of 1 vCPU and 2 GB around the clock.
FLAT = [
    (
        "AmazonECS",
        PROD,
        f"arn:aws:ecs:{REGION}:{PROD}:service/storefront/storefront-web",
        "USE1-Fargate-vCPU-Hours:perCPU",
        "FargateTask",
        ("354.60", "354.60", "354.60"),
        True,
        tags("storefront-web", "storefront", "prod", "digital"),
    ),
    (
        "AmazonECS",
        PROD,
        f"arn:aws:ecs:{REGION}:{PROD}:service/storefront/storefront-web",
        "USE1-Fargate-GB-Hours",
        "FargateTask",
        ("77.88", "77.88", "77.88"),
        True,
        tags("storefront-web", "storefront", "prod", "digital"),
    ),
    (
        "AWSLambda",
        PROD,
        f"arn:aws:lambda:{REGION}:{PROD}:function:image-resizer",
        "Lambda-GB-Second",
        "Invoke",
        ("120", "130", "140"),
        True,
        tags("image-resizer", "image-resizer", "prod", "digital"),
    ),
    (
        "AmazonDynamoDB",
        PROD,
        f"arn:aws:dynamodb:{REGION}:{PROD}:table/cart",
        "PayPerRequestThroughput",
        "PayPerRequest",
        ("860", "880", "900"),
        False,
        tags("cart", "storefront", "prod", "digital"),
    ),
    (
        "AmazonS3",
        PROD,
        "harbor-goods-product-images",
        "Requests-Tier1",
        "PutObject",
        ("45", "48", "50"),
        False,
        tags("", "storefront", "prod", "digital"),
    ),
]


# --- Row builders -------------------------------------------------------------
def row(
    period,
    acct,
    line_type,
    service,
    resource,
    usage_type,
    operation,
    usage,
    od_cost,
    cost,
    tag,
    itype="",
    term="OnDemand",
) -> dict[str, str]:
    base = {
        "bill_billing_period": period,
        "line_item_usage_account_id": acct,
        "line_item_line_item_type": line_type,
        "product_servicecode": service,
        "line_item_resource_id": resource,
        "line_item_usage_type": usage_type,
        "line_item_operation": operation,
        "product_instance_type": itype,
        "product_region_code": REGION,
        "pricing_term": term,
        "line_item_usage_amount": str(usage),
        "pricing_public_on_demand_cost": cents(od_cost),
        "line_item_unblended_cost": cents(cost),
    }
    base.update(tag)
    return base


def usage_row(period, acct, service, resource, usage_type, operation, usage, rate, tag, itype=""):
    cost = d(usage) * d(rate)
    return row(period, acct, "Usage", service, resource, usage_type, operation, usage, cost, cost, tag, itype)


def build_cur() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    inst = instances()
    by_name = {i["name"]: i for i in inst}
    for p_index, period in enumerate(PERIODS):
        # EC2 instance hours
        for i in inst:
            if period not in i["periods"]:
                continue
            od = HOURS * d(RATE["ec2"][i["type"]])
            ut = f"BoxUsage:{i['type']}"
            if i["sp"]:
                rows.append(
                    row(
                        period,
                        i["account"],
                        "SavingsPlanCoveredUsage",
                        "AmazonEC2",
                        i["id"],
                        ut,
                        "RunInstances",
                        HOURS,
                        od,
                        od,
                        i["tags"],
                        i["type"],
                        "SavingsPlan",
                    )
                )
                rows.append(
                    row(
                        period,
                        i["account"],
                        "SavingsPlanNegation",
                        "AmazonEC2",
                        i["id"],
                        ut,
                        "RunInstances",
                        0,
                        d(0),
                        -od,
                        i["tags"],
                        i["type"],
                        "SavingsPlan",
                    )
                )
            else:
                rows.append(
                    row(
                        period,
                        i["account"],
                        "Usage",
                        "AmazonEC2",
                        i["id"],
                        ut,
                        "RunInstances",
                        HOURS,
                        od,
                        od,
                        i["tags"],
                        i["type"],
                    )
                )
        rows.append(
            row(
                period,
                PROD,
                "SavingsPlanRecurringFee",
                "ComputeSavingsPlans",
                SP_ARN,
                "ComputeSP:1yrNoUpfront",
                "",
                HOURS,
                d(0),
                HOURS * SP_COMMITMENT,
                tags(),
            )
        )
        # Attached EBS volumes
        for owner, vid, vtype, gb in ATTACHED_VOLUMES:
            i = by_name[owner]
            if period in i["periods"]:
                rows.append(
                    usage_row(
                        period,
                        i["account"],
                        "AmazonEC2",
                        vid,
                        f"EBS:VolumeUsage.{vtype}",
                        f"CreateVolume-{vtype.capitalize()}",
                        gb,
                        RATE["ebs"][vtype],
                        i["tags"],
                    )
                )
        for vid, acct, vtype, gb, periods, _ in UNATTACHED_VOLUMES:
            if period in periods:
                rows.append(
                    usage_row(
                        period,
                        acct,
                        "AmazonEC2",
                        vid,
                        f"EBS:VolumeUsage.{vtype}",
                        f"CreateVolume-{vtype.capitalize()}",
                        gb,
                        RATE["ebs"][vtype],
                        tags(),
                    )
                )
        for sid, acct, _, gb, _, _ in SNAPSHOTS:
            arn = f"arn:aws:ec2:{REGION}:{acct}:snapshot/{sid}"
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonEC2",
                    arn,
                    "EBS:SnapshotUsage",
                    "CreateSnapshot",
                    gb,
                    RATE["ebs"]["snapshot"],
                    tags(),
                )
            )
        for alloc, acct, _ in IDLE_EIPS:
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonVPC",
                    alloc,
                    "PublicIPv4:IdleAddress",
                    "AllocateAddressVPC",
                    HOURS,
                    RATE["idle_ipv4_hour"],
                    tags(),
                )
            )
        for name, acct, kind, lcu, _, tag in LOAD_BALANCERS:
            if kind == "application":
                arn = f"arn:aws:elasticloadbalancing:{REGION}:{acct}:loadbalancer/app/{name}/0a0b0c0d0e0f0001"
                rows.append(
                    usage_row(
                        period,
                        acct,
                        "AWSELB",
                        arn,
                        "LoadBalancerUsage",
                        "LoadBalancing:Application",
                        HOURS,
                        RATE["alb_hour"],
                        tag,
                    )
                )
                rows.append(
                    usage_row(
                        period,
                        acct,
                        "AWSELB",
                        arn,
                        "LCUUsage",
                        "LoadBalancing:Application",
                        lcu[p_index],
                        RATE["lcu"],
                        tag,
                    )
                )
            else:
                arn = f"arn:aws:elasticloadbalancing:{REGION}:{acct}:loadbalancer/{name}"
                rows.append(
                    usage_row(
                        period, acct, "AWSELB", arn, "LoadBalancerUsage", "LoadBalancing", HOURS, RATE["clb_hour"], tag
                    )
                )
        for nid, acct, _, gb, tag in NAT_GATEWAYS:
            arn = f"arn:aws:ec2:{REGION}:{acct}:natgateway/{nid}"
            rows.append(
                usage_row(
                    period, acct, "AmazonEC2", arn, "NatGateway-Hours", "NatGateway", HOURS, RATE["nat_hour"], tag
                )
            )
            rows.append(
                usage_row(
                    period, acct, "AmazonEC2", arn, "NatGateway-Bytes", "NatGateway", gb[p_index], RATE["nat_gb"], tag
                )
            )
        for db, acct, cls, multi, gb, io_millions, tag in RDS:
            arn = f"arn:aws:rds:{REGION}:{acct}:cluster:{db}"
            instances_in_cluster = 2 if multi else 1
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonRDS",
                    arn,
                    f"InstanceUsage:{cls.replace('xlarge', 'xl')}",  # the CUR abbreviates, e.g. db.r5.2xl
                    "CreateDBInstance:0021",
                    HOURS * instances_in_cluster,
                    RATE["rds"][cls],
                    tag,
                    cls,
                )
            )
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonRDS",
                    arn,
                    "Aurora:StorageUsage",
                    "CreateDBInstance:0021",
                    gb,
                    RATE["aurora_storage"],
                    tag,
                )
            )
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonRDS",
                    arn,
                    "Aurora:StorageIOUsage",
                    "CreateDBInstance:0021",
                    io_millions * 1_000_000,
                    RATE["aurora_io"],
                    tag,
                )
            )
        for n in (1, 2):
            arn = f"arn:aws:elasticache:{REGION}:{PROD}:cluster:sessions-00{n}"
            rows.append(
                usage_row(
                    period,
                    PROD,
                    "AmazonElastiCache",
                    arn,
                    "NodeUsage:cache.r5.large",
                    "CreateCacheCluster:0002",
                    HOURS,
                    RATE["cache.r5.large"],
                    tags(f"sessions-00{n}", "storefront", "", "digital"),
                    "cache.r5.large",
                )
            )
        for n in (1, 2):
            arn = f"arn:aws:redshift:{REGION}:{PROD}:cluster:warehouse"
            rows.append(
                usage_row(
                    period,
                    PROD,
                    "AmazonRedshift",
                    f"{arn}/node-{n}",
                    "Node:ra3.xlplus",
                    "RunComputeNode:0001",
                    HOURS,
                    RATE["redshift.ra3.xlplus"],
                    tags("warehouse", "analytics", "prod", "finance"),
                    "ra3.xlplus",
                )
            )
        for name, acct, _, _, ingest, stored, tag in LOG_GROUPS:
            arn = f"arn:aws:logs:{REGION}:{acct}:log-group:{name}"
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonCloudWatch",
                    arn,
                    "DataProcessing-Bytes",
                    "PutLogEvents",
                    ingest[p_index],
                    RATE["logs_ingest"],
                    tag,
                )
            )
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonCloudWatch",
                    arn,
                    "TimedStorage-ByteHrs",
                    "HourlyStorageMetering",
                    stored[p_index],
                    RATE["logs_storage"],
                    tag,
                )
            )
        for name, acct, gb, tag in BUCKETS:
            rows.append(
                usage_row(
                    period,
                    acct,
                    "AmazonS3",
                    name,
                    "TimedStorage-ByteHrs",
                    "StandardStorage",
                    gb[p_index],
                    RATE["s3_standard"],
                    tag,
                )
            )
        rows.append(
            usage_row(
                period,
                PROD,
                "AWSDataTransfer",
                "",
                "DataTransfer-Out-Bytes",
                "",
                (8000, 9000, 10000)[p_index],
                RATE["transfer_out"],
                tags(),
            )
        )
        rows.append(
            usage_row(
                period,
                PROD,
                "AmazonCloudFront",
                f"arn:aws:cloudfront::{PROD}:distribution/E0HARBOR0001",
                "US-DataTransfer-Out-Bytes",
                "GET",
                (28000, 29000, 30000)[p_index],
                RATE["cloudfront_out"],
                tags("storefront-cdn", "storefront", "prod", ""),
            )
        )
        for service, acct, res, ut, op, costs, _, tag in FLAT:
            cost = d(costs[p_index])
            rows.append(row(period, acct, "Usage", service, res, ut, op, 1, cost, cost, tag))
    rows.sort(
        key=lambda r: (
            r["bill_billing_period"],
            r["line_item_usage_account_id"],
            r["product_servicecode"],
            r["line_item_resource_id"],
            r["line_item_usage_type"],
            r["line_item_line_item_type"],
        )
    )
    return rows


# --- Recommendation and inventory exports ------------------------------------
def ec2_arn(acct: str, iid: str) -> str:
    return f"arn:aws:ec2:{REGION}:{acct}:instance/{iid}"


def compute_optimizer_ec2() -> dict:
    recs = []
    cpu_mem = {
        "report": ("Optimized", "41.0", "58.0", None),
        "app": ("Overprovisioned", "17.0", "34.0", ("m5.xlarge", "LOW")),
        "batch": ("Optimized", "88.0", "61.0", None),
        "stg-app": ("Optimized", "65.0", "48.0", None),
        "ci-runner": ("Optimized", "92.0", "40.0", None),
    }
    for i in instances():
        prefix = i["name"].rsplit("-", 1)[0]
        if prefix not in cpu_mem:
            continue
        finding, cpu, mem, target = cpu_mem[prefix]
        options = []
        if target:
            itype, risk = target
            saving = HOURS * (d(RATE["ec2"][i["type"]]) - d(RATE["ec2"][itype]))
            options.append(
                {
                    "instanceType": itype,
                    "rank": 1,
                    "performanceRisk": risk,
                    "projectedUtilizationMetrics": [
                        {"name": "CPU", "statistic": "MAXIMUM", "value": float(d(cpu) * 2)}
                    ],
                    "savingsOpportunity": {"estimatedMonthlySavings": {"currency": "USD", "value": float(saving)}},
                }
            )
        recs.append(
            {
                "instanceArn": ec2_arn(i["account"], i["id"]),
                "accountId": i["account"],
                "instanceName": i["name"],
                "currentInstanceType": i["type"],
                "finding": finding,
                "lookBackPeriodInDays": 14,
                "utilizationMetrics": [
                    {"name": "CPU", "statistic": "MAXIMUM", "value": float(cpu)},
                    {"name": "MEMORY", "statistic": "MAXIMUM", "value": float(mem)},
                ],
                "recommendationOptions": options,
            }
        )
    return {"instanceRecommendations": recs}


def compute_optimizer_rds() -> dict:
    plan = {
        "orders-db": ("Overprovisioned", "22.0", {"dbInstanceClass": "db.r5.2xlarge", "multiAZ": True}, "LOW"),
        "reporting-db": ("Optimized", "58.0", None, None),
        "orders-db-stg": ("Overprovisioned", "6.0", {"dbInstanceClass": "db.r5.large", "multiAZ": False}, "LOW"),
    }
    recs = []
    for db, acct, cls, multi, _, _, _ in RDS:
        finding, cpu, target, risk = plan[db]
        options = []
        if target:
            options.append({**target, "rank": 1, "performanceRisk": risk})
        recs.append(
            {
                "resourceArn": f"arn:aws:rds:{REGION}:{acct}:cluster:{db}",
                "accountId": acct,
                "engine": "aurora-postgresql",
                "currentDBInstanceClass": cls,
                "multiAZ": multi,
                "instanceFinding": finding,
                "lookBackPeriodInDays": 14,
                "utilizationMetrics": [{"name": "CPU", "statistic": "MAXIMUM", "value": float(cpu)}],
                "instanceRecommendationOptions": options,
            }
        )
    return {"rdsDBRecommendations": recs}


def trusted_advisor() -> dict:
    low_util = [i for i in instances() if i["name"] in ("dev-04", "dev-05")]
    vol_owner = {vid: owner for owner, vid, _, _ in ATTACHED_VOLUMES}
    return {
        "checks": [
            {
                "name": "Low Utilization Amazon EC2 Instances",
                "status": "warning",
                "flaggedResources": [
                    {
                        "resourceId": i["id"],
                        "accountId": i["account"],
                        "region": REGION,
                        "metadata": {
                            "instanceName": i["name"],
                            "instanceType": i["type"],
                            "fourteenDayAverageCpuPercent": 1.2,
                            "fourteenDayAverageNetworkIoMb": 0.4,
                            "attachedVolumes": [v for v, o in vol_owner.items() if o == i["name"]],
                        },
                    }
                    for i in low_util
                ],
            },
            {
                "name": "Underutilized Amazon EBS Volumes",
                "status": "warning",
                "flaggedResources": [
                    {
                        "resourceId": vid,
                        "accountId": acct,
                        "region": REGION,
                        "metadata": {"volumeType": vtype, "sizeGiB": gb, "state": "available", "note": note},
                    }
                    for vid, acct, vtype, gb, _, note in UNATTACHED_VOLUMES
                ],
            },
            {
                "name": "Unassociated Elastic IP Addresses",
                "status": "warning",
                "flaggedResources": [
                    {"resourceId": alloc, "accountId": acct, "region": REGION, "metadata": {"publicIp": ip}}
                    for alloc, acct, ip in IDLE_EIPS
                ],
            },
            {
                "name": "Idle Load Balancers",
                "status": "warning",
                "flaggedResources": [
                    {
                        "resourceId": name,
                        "accountId": acct,
                        "region": REGION,
                        "metadata": {"type": kind, "requestsLast14Days": req, "reason": "No requests"},
                    }
                    for name, acct, kind, _, req, _ in LOAD_BALANCERS
                    if req == 0
                ],
            },
            {"name": "Amazon EC2 Reserved Instances Optimization", "status": "ok", "flaggedResources": []},
        ]
    }


def snapshots_inventory() -> dict:
    return {
        "Snapshots": [
            {
                "SnapshotId": sid,
                "OwnerId": acct,
                "VolumeId": vol,
                "BilledSizeGiB": gb,
                "AgeDays": age,
                "Tags": [{"Key": "retention", "Value": ret}] if ret else [],
            }
            for sid, acct, vol, gb, age, ret in SNAPSHOTS
        ]
    }


def log_groups_inventory() -> dict:
    return {
        "logGroups": [
            {
                "logGroupName": name,
                "accountId": acct,
                "class": cls,
                "retentionInDays": ret,
                "monthlyIngestGB": ingest[-1],
                "storedGB": stored[-1],
            }
            for name, acct, cls, ret, ingest, stored, _ in LOG_GROUPS
        ]
    }


def nat_inventory() -> dict:
    return {
        "NatGateways": [
            {
                "NatGatewayId": nid,
                "AccountId": acct,
                "AvailabilityZone": az,
                "Environment": tag["resource_tags_user_environment"],
            }
            for nid, acct, az, _, tag in NAT_GATEWAYS
        ]
    }


def savings_plans_inventory() -> dict:
    return {
        "savingsPlans": [
            {
                "savingsPlanArn": SP_ARN,
                "savingsPlanType": "Compute",
                "paymentOption": "No Upfront",
                "termDurationInSeconds": 31536000,
                "commitment": str(SP_COMMITMENT),
                "currency": "USD",
                "state": "active",
                "utilizationPercentage": "100.0",
            }
        ]
    }


def s3_age_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["bucket", "storage_class", "age_band_days", "size_gb", "object_count"])
    for band, gb, objs in LOG_BUCKET_AGE:
        w.writerow(["harbor-goods-app-logs", "STANDARD", band, gb, objs])
    return buf.getvalue()


def cur_csv() -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(build_cur())
    return buf.getvalue()


def dump(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"


def outputs() -> dict[str, str]:
    """Relative path -> file content for every generated file."""
    return {
        "cur/cost-and-usage.csv": cur_csv(),
        "compute-optimizer/ec2-instance-recommendations.json": dump(compute_optimizer_ec2()),
        "compute-optimizer/rds-recommendations.json": dump(compute_optimizer_rds()),
        "trusted-advisor/cost-optimizing-checks.json": dump(trusted_advisor()),
        "inventory/ebs-snapshots.json": dump(snapshots_inventory()),
        "inventory/images.json": dump({"Images": AMIS}),
        "inventory/cloudwatch-log-groups.json": dump(log_groups_inventory()),
        "inventory/nat-gateways.json": dump(nat_inventory()),
        "inventory/savings-plans.json": dump(savings_plans_inventory()),
        "inventory/s3-storage-by-age.csv": s3_age_csv(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "synthetic"))
    parser.add_argument("--check", action="store_true", help="fail if the files on disk differ; write nothing")
    args = parser.parse_args()
    out = Path(args.out)
    stale = []
    for rel, content in outputs().items():
        path = out / rel
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")
    if stale:
        print(f"stale synthetic data: {', '.join(stale)}. Run `make data`.", file=sys.stderr)
        return 1
    if args.check:
        print("data/synthetic matches the generator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
