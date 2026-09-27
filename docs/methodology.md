# Methodology

The Harbor Goods audit uses read-only exports to produce a ranked list of savings estimates.
Results appear in `report/REPORT.md`; the method below lets reviewers verify the analysis or
apply it to a real account.

## Inputs

| Input | File | Real-world source |
| --- | --- | --- |
| Cost and Usage Report extract | `data/synthetic/cur/cost-and-usage.csv` | CUR 2.0 data export, aggregated per resource and billing period |
| EC2 and RDS recommendations | `data/synthetic/compute-optimizer/*.json` | `aws compute-optimizer get-ec2-instance-recommendations`, `get-rds-database-recommendations` |
| Idle and unattached resources | `data/synthetic/trusted-advisor/cost-optimizing-checks.json` | Trusted Advisor cost-optimizing checks |
| Snapshots, AMIs, log groups, NAT gateways, Savings Plans | `data/synthetic/inventory/*.json` | `describe-snapshots`, `describe-images`, `describe-log-groups`, `describe-nat-gateways`, `describe-savings-plans` |
| S3 storage by age | `data/synthetic/inventory/s3-storage-by-age.csv` | S3 Inventory or Storage Lens, grouped by object age |
| Unit prices, thresholds, ratings | `data/assumptions.json` | AWS Price List API, client policy, auditor judgment |

All exports in this sample contain synthetic data, as documented in
[ADR 0001](adr/0001-generate-synthetic-exports.md).

## Steps

1. **Calculate the spending breakdown.** The analysis groups net unblended cost by service and
   account within each billing period and calculates the change between the first and last
   periods. Savings Plan negation lines offset covered usage; the resulting net cost represents
   Harbor Goods' actual payment.
2. **Identify unused resources.** Trusted Advisor identifies idle and unattached resources, which
   the scripts price using their CUR lines. Snapshots qualify under a separate rule only when
   they exceed the age threshold, have no retention tag and are not used by an AMI.
3. **Adjust capacity and operating hours.** For every over-provisioned Compute Optimizer finding,
   the scripts price the rank-1 recommendation using on-demand rates. The staging schedule limits
   operation to working hours.
4. **Revise storage, logging and networking.** Changes include converting gp2 to gp3 while
   preserving gp2 throughput, adjusting log retention and DEBUG logging, applying an S3 lifecycle
   rule and consolidating NAT gateways. Estimates deduct any fees introduced by each change;
   one-time costs appear separately.
5. **Calculate commitments after other changes.** CUR line types determine coverage. A new Compute
   Savings Plan covers the steady baseline remaining after the changes, using the discount
   observed on the existing plan. Production RDS coverage uses Reserved Instances sized after
   the resize ([ADR 0003](adr/0003-size-commitments-last.md)).
6. **Prioritize and categorize findings.** Estimated monthly savings determine the ranking.
   `data/assumptions.json` records each item's effort and risk ratings and their rationale.
   An item qualifies as a quick win only when both ratings are low; all others fall under
   planned work.
7. **Assess required tags.** The analysis calculates the proportion of spend carrying each required
   tag. It distinguishes untagged resources that tagging can address from data transfer and
   commitment fees that require allocation rules.
8. **Generate and validate outputs.** A single run renders both the report and its evidence
   ([ADR 0002](adr/0002-render-report-from-template.md)). Tests independently recalculate every
   figure using hand arithmetic.

## Rules that keep the numbers honest

- The CUR supplies all current costs; recommendation tools determine targets only.
- Calculations use `Decimal` for money. Findings are individually rounded to the cent before
  those rounded amounts are summed into totals.
- Two findings may include the same resource only when they estimate separate cost components.
  The sole instance is the order-api log group: retention reduces storage costs, while changing
  DEBUG logging reduces ingestion costs.
- Savings carry an estimate label throughout. None of the results represents measured savings.

## Adapting it to a real account

- Use real exports with the same shape in place of `data/synthetic/`, and update the prices in
  `data/assumptions.json` using Price List API values for the client's regions.
- Follow `make test-live` for a read-only check that exporters continue to provide the fields
  consumed by the loader.
- Account for cases beyond this sample, including several Savings Plans, existing Reserved
  Instances, Spot usage, multiple regions and Marketplace charges. For unsupported cases,
  including more than one existing Savings Plan, the scripts return an error and stop without
  guessing.
