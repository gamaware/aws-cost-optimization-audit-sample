# Harbor Goods: AWS cost optimization audit

<!-- `make evidence` generates this file from report/REPORT.template.md. Make edits in the template. -->

> **Fictional sample.** Harbor Goods is an invented retailer. This repository uses synthetic billing
> records, recommendations and inventories; all savings figures estimate outcomes from those
> fictional inputs. The report represents neither an actual company nor measured results.

| Item | Value |
| --- | --- |
| Client | Harbor Goods (fictional mid-size retailer) |
| Scope | 3 AWS accounts in one AWS Organization, region `us-east-1` |
| Billing window | M1 to M3 (three monthly billing periods, oldest first) |
| Analysis period | M3, net unblended cost $23,033.64 |
| Access used | Read-only exports; no change was made to any account |
| Deliverable | This report, `evidence/` and the scripts that produced both |

## 1. Executive summary

AWS spending for Harbor Goods reached $23,033.64 in M3, an increase of
10.5% ($2,194.08) from M1. Across 16 opportunities,
the audit estimates savings of **$7,666.87 a month ($92,002.44 a year)**,
equivalent to 33.3% of the M3 bill. Completing every recommendation would bring
monthly costs for the same workload to approximately $15,366.77.

- **10 quick wins** offer $3,742.22 in monthly savings at low effort and low
  risk. Most involve removing idle resources or changing a single setting; a platform engineer can
  complete these within a week.
- **6 planned items** offer $3,924.65 in monthly savings. Each requires
  a load test, release or one-year commitment and therefore needs a change ticket and rollback plan.
- One-time expenses of $1,012.50 cover rollback snapshots for volume deletions and S3
  lifecycle transition requests. Each expense pays back within a few months.

The largest three opportunities account for these estimated monthly savings:

1. **SAV-02: Rightsize the production orders database** reduces monthly costs by $1,460.00.
2. **SAV-03: Rightsize the staging orders database and drop Multi-AZ** reduces monthly costs by $1,335.00.
3. **SAV-01: Rightsize over-provisioned EC2 instances** reduces monthly costs by $840.96.

Incomplete tagging also limits cost allocation: `cost-center` appears on only 78.1%
of spending in M3. Finance therefore cannot yet provide individual team bills.
Section 9 describes the corrective work.

## 2. Scope and method

Only exports inform this audit, matching the files a client would supply through read-only access:

- **Cost and Usage Report (CUR 2.0 columns)**: `data/synthetic/cur/` contains 372 line
  items covering 13 services, aggregated by resource and billing period.
- **AWS Compute Optimizer**: recommendations for EC2 and RDS based on a 14-day look-back.
- **AWS Trusted Advisor**: cost-optimization checks identifying idle and unattached resources.
- **Inventories**: records of EBS snapshots, AMIs, CloudWatch log groups, NAT gateways and the
  existing Savings Plan, plus the log bucket's S3 storage-by-age report.

The calculations follow these rules:

1. The CUR for M3 supplies every current cost. Recommendation tools identify candidate
   resources but supply no dollar figures.
2. Unit prices from `data/assumptions.json` determine target costs. These approximate on-demand
   list pricing in us-east-1; an actual engagement obtains prices from the AWS Price List API.
3. Each recommendation's monthly savings round to the nearest cent. Multiplying that rounded
   amount by twelve gives annual savings. Totals sum the rounded amounts, keeping tables exact.
4. Commitment sizing follows all other changes and uses only the remaining usage, preventing
   double counting of savings (section 7).
5. `data/assumptions.json` includes the effort and risk ratings and their rationale. An item
   qualifies as a quick win only when both ratings are low; all others require planned work.

The extract excludes tax, credits, refunds, AWS Support charges and Marketplace purchases, so
these fall outside the audit. Architecture changes requiring redesign and pricing outside
us-east-1 are also beyond scope.

## 3. Where the money goes

| Service | M1 | M2 | M3 | Change M1 to M3 | Share of M3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Amazon EC2 (instances, EBS, NAT) | $6,385.67 | $7,758.95 | $7,785.95 | $1,400.28 (21.9%) | 33.8% |
| Amazon RDS | $5,147.50 | $5,147.50 | $5,147.50 | $0.00 (0.0%) | 22.3% |
| Amazon CloudFront | $2,380.00 | $2,465.00 | $2,550.00 | $170.00 (7.1%) | 11.1% |
| Amazon CloudWatch | $1,345.00 | $1,486.00 | $1,627.00 | $282.00 (21.0%) | 7.1% |
| Amazon Redshift | $1,585.56 | $1,585.56 | $1,585.56 | $0.00 (0.0%) | 6.9% |
| Amazon S3 | $1,448.00 | $1,497.00 | $1,545.00 | $97.00 (6.7%) | 6.7% |
| All other (7 services) | $2,547.83 | $2,671.03 | $2,792.63 | $244.80 (9.6%) | 12.1% |
| **Total** | **$20,839.56** | **$22,611.04** | **$23,033.64** | **$2,194.08 (10.5%)** | **100.0%** |

Spending increased $2,194.08 across the billing window, with the largest changes in:

- Amazon EC2 (instances, EBS, NAT), which rose $1,400.28 as the production order-api fleet expanded from
  4 to 6 instances and staging expanded from
  2 to 4.
- Amazon CloudWatch, which rose $282.00 as log groups without expiration continued accumulating
  data each month.
- Data transfer, which rose $180.00 alongside monthly increases in production internet egress.

The account breakdown follows:

| Account | M1 | M2 | M3 | Change M1 to M3 | Share of M3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `111122223333` (production) | $16,727.29 | $17,762.63 | $18,134.73 | $1,407.44 (8.4%) | 78.7% |
| `444455556666` (staging) | $2,871.24 | $3,536.38 | $3,540.88 | $669.64 (23.3%) | 15.4% |
| `123456789012` (shared services) | $1,241.03 | $1,312.03 | $1,358.03 | $117.00 (9.4%) | 5.9% |

## 4. Ranked savings

The following ranking orders recommendations by estimated monthly savings from fictional data.
Recommendation IDs remain unchanged when ranks move. `evidence/savings-detail.csv` provides the
calculations for individual resources.

| Rank | ID | Recommendation | Monthly | Annual | One-time cost | Effort | Risk | Type |
| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | SAV-02 | Rightsize the production orders database | $1,460.00 | $17,520.00 | none | Medium | Medium | Planned work |
| 2 | SAV-03 | Rightsize the staging orders database and drop Multi-AZ | $1,335.00 | $16,020.00 | none | Low | Low | Quick win |
| 3 | SAV-01 | Rightsize over-provisioned EC2 instances | $840.96 | $10,091.52 | none | Medium | Medium | Planned work |
| 4 | SAV-04 | Run staging order-api instances on a working-hours schedule | $721.92 | $8,663.04 | none | Low | Low | Quick win |
| 5 | SAV-15 | Buy a one-year Compute Savings Plan for the steady EC2 baseline | $651.29 | $7,815.48 | none | Low | Medium | Planned work |
| 6 | SAV-16 | Buy one-year RDS Reserved Instances for production after the resize | $547.50 | $6,570.00 | none | Low | Medium | Planned work |
| 7 | SAV-11 | Set CloudWatch Logs retention on groups that never expire | $539.55 | $6,474.60 | none | Low | Low | Quick win |
| 8 | SAV-05 | Delete unattached EBS volumes after a rollback snapshot | $385.00 | $4,620.00 | $212.50 | Low | Low | Quick win |
| 9 | SAV-13 | Move application logs older than 30 days to S3 Glacier Instant Retrieval | $378.50 | $4,542.00 | $800.00 | Low | Low | Quick win |
| 10 | SAV-12 | Turn off DEBUG logging in production order-api | $360.00 | $4,320.00 | none | Medium | Low | Planned work |
| 11 | SAV-10 | Stop, then terminate idle untagged instances | $141.47 | $1,697.64 | none | Low | Low | Quick win |
| 12 | SAV-07 | Delete EBS snapshots older than 180 days | $122.50 | $1,470.00 | none | Low | Low | Quick win |
| 13 | SAV-06 | Change attached gp2 volumes to gp3 | $69.00 | $828.00 | none | Low | Low | Quick win |
| 14 | SAV-14 | Consolidate staging NAT gateways to one | $64.90 | $778.80 | none | Medium | Low | Planned work |
| 15 | SAV-09 | Delete idle load balancers | $34.68 | $416.16 | none | Low | Low | Quick win |
| 16 | SAV-08 | Release unassociated Elastic IP addresses | $14.60 | $175.20 | none | Low | Low | Quick win |
| | | **Total** | **$7,666.87** | **$92,002.44** | **$1,012.50** | | | |

## 5. Quick wins versus planned work

**Quick wins: $3,742.22 monthly ($44,906.64 annually).** Complete these before planned
work, following rank order within a single change window. Every item either supports a direct
reversal or retains a snapshot until validation confirms the change.

| ID | Recommendation | Monthly | Why this effort and risk |
| --- | --- | ---: | --- |
| SAV-03 | Rightsize the staging orders database and drop Multi-AZ | $1,335.00 | Staging only; a short outage during the modification is acceptable. |
| SAV-04 | Run staging order-api instances on a working-hours schedule | $721.92 | Instance Scheduler or an EventBridge schedule; staging is idle outside working hours. |
| SAV-11 | Set CloudWatch Logs retention on groups that never expire | $539.55 | One setting per log group; export anything under a compliance hold first. |
| SAV-05 | Delete unattached EBS volumes after a rollback snapshot | $385.00 | Snapshot each volume first, then delete; the snapshot is the rollback. |
| SAV-13 | Move application logs older than 30 days to S3 Glacier Instant Retrieval | $378.50 | One lifecycle rule; reads of older logs are rare and remain immediate in Glacier Instant Retrieval. |
| SAV-10 | Stop, then terminate idle untagged instances | $141.47 | No owner tag and about 1% CPU; stop, wait one week for a claim, then terminate. |
| SAV-07 | Delete EBS snapshots older than 180 days | $122.50 | Only snapshots older than the threshold, not used by an AMI and without a retention tag. |
| SAV-06 | Change attached gp2 volumes to gp3 | $69.00 | Elastic Volumes change the type online, with no detach and no downtime. |
| SAV-09 | Delete idle load balancers | $34.68 | No requests in 14 days; delete after checking DNS. |
| SAV-08 | Release unassociated Elastic IP addresses | $14.60 | Release after confirming no DNS record or allow list points at the address. |

**Planned work: $3,924.65 monthly ($47,095.80 annually).** Follow this order:

1. Complete rightsizing (SAV-02, SAV-01) before purchasing
   commitments. Each resize requires a load test and maintenance window, with a return to the
   previous instance class available for rollback.
2. Purchase commitments (SAV-15, SAV-16) against the
   resulting usage. An earlier purchase would commit to the oversized fleet for one year.
3. Include the logging update (SAV-12) in the next order-api release. Implement
   staging NAT gateway consolidation (SAV-14) through the staging network code.

| ID | Recommendation | Monthly | Why this effort and risk |
| --- | --- | ---: | --- |
| SAV-02 | Rightsize the production orders database | $1,460.00 | Class change causes a Multi-AZ failover; schedule it in a maintenance window after a load test. |
| SAV-01 | Rightsize over-provisioned EC2 instances | $840.96 | Instance type change needs a rolling replacement and a load test on memory headroom. |
| SAV-15 | Buy a one-year Compute Savings Plan for the steady EC2 baseline | $651.29 | A one-year commitment; buy it after rightsizing so it does not lock in oversized usage. |
| SAV-16 | Buy one-year RDS Reserved Instances for production after the resize | $547.50 | A one-year commitment; buy it after the orders-db resize. |
| SAV-12 | Turn off DEBUG logging in production order-api | $360.00 | Needs an application config change and a release of order-api. |
| SAV-14 | Consolidate staging NAT gateways to one | $64.90 | Route table changes in staging; an AZ outage would cut staging egress, which is acceptable. |

## 6. Idle, unattached and rightsizing findings

### 6.1 Idle and unattached resources

These resources come from Trusted Advisor findings. Snapshot selection applies an additional
rule: snapshots must exceed 180 days in age, have no AMI reference and carry no
`retention` tag. This excludes 1 legal-hold snapshot and 2
snapshots backing AMIs.

| ID | Account | Resource | Detail | Current/mo | Target/mo | Saving/mo |
| --- | --- | --- | --- | ---: | ---: | ---: |
| SAV-05 | `111122223333` | `vol-0a9000000000000e1` | gp2, 1,000 GiB, left over from the app fleet rebuild | $100.00 | $0.00 | $100.00 |
| SAV-05 | `111122223333` | `vol-0a9000000000000e2` | gp2, 500 GiB, detached test restore | $50.00 | $0.00 | $50.00 |
| SAV-05 | `444455556666` | `vol-0b9000000000000e1` | gp2, 500 GiB, old staging database volume | $50.00 | $0.00 | $50.00 |
| SAV-05 | `123456789012` | `vol-0c9000000000000e1` | gp3, 2,000 GiB, retired build cache | $160.00 | $0.00 | $160.00 |
| SAV-05 | `123456789012` | `vol-0c9000000000000e2` | gp2, 250 GiB, detached from a terminated dev box | $25.00 | $0.00 | $25.00 |
| SAV-07 | `111122223333` | `snap-0a1000000000000004` | 900 GiB billed, 420 days old | $45.00 | $0.00 | $45.00 |
| SAV-07 | `111122223333` | `snap-0a1000000000000006` | 650 GiB billed, 610 days old | $32.50 | $0.00 | $32.50 |
| SAV-07 | `444455556666` | `snap-0b1000000000000001` | 400 GiB billed, 300 days old | $20.00 | $0.00 | $20.00 |
| SAV-07 | `123456789012` | `snap-0c1000000000000001` | 500 GiB billed, 250 days old | $25.00 | $0.00 | $25.00 |
| SAV-08 | `111122223333` | `eipalloc-0a1000000000000001` | public IP 203.0.113.10 | $3.65 | $0.00 | $3.65 |
| SAV-08 | `111122223333` | `eipalloc-0a1000000000000002` | public IP 203.0.113.11 | $3.65 | $0.00 | $3.65 |
| SAV-08 | `444455556666` | `eipalloc-0b1000000000000001` | public IP 203.0.113.20 | $3.65 | $0.00 | $3.65 |
| SAV-08 | `123456789012` | `eipalloc-0c1000000000000001` | public IP 203.0.113.30 | $3.65 | $0.00 | $3.65 |
| SAV-09 | `111122223333` | `legacy-promo-alb` | application, 0 requests in 14 days | $16.43 | $0.00 | $16.43 |
| SAV-09 | `444455556666` | `stg-legacy-clb` | classic, 0 requests in 14 days | $18.25 | $0.00 | $18.25 |
| SAV-10 | `123456789012` | `i-0c200000000000004` | dev-04 (t3.large), 1.2% average CPU | $60.74 | $0.00 | $60.74 |
| SAV-10 | `123456789012` | `vol-0c200000000000004` | root volume of dev-04 | $10.00 | $0.00 | $10.00 |
| SAV-10 | `123456789012` | `i-0c200000000000005` | dev-05 (t3.large), 1.2% average CPU | $60.74 | $0.00 | $60.74 |
| SAV-10 | `123456789012` | `vol-0c200000000000005` | root volume of dev-05 | $10.00 | $0.00 | $10.00 |

Create a snapshot of every one of the 5 unattached volumes before deletion,
then retain those snapshots for one month. The one-time cost is $212.50,
an upper bound assuming full volume size, with payback in 0.6 months.

### 6.2 Rightsizing and scheduling

Compute Optimizer classified both orders databases and the order-api instances as
over-provisioned. Because staging order-api instances handle working-day activity, the
recommendation schedules 260 running hours per month while retaining their
current instance type.

| ID | Account | Resource | Detail | Current/mo | Target/mo | Saving/mo |
| --- | --- | --- | --- | ---: | ---: | ---: |
| SAV-01 | `111122223333` | `i-0a200000000000001` | app-01: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-01 | `111122223333` | `i-0a200000000000002` | app-02: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-01 | `111122223333` | `i-0a200000000000003` | app-03: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-01 | `111122223333` | `i-0a200000000000004` | app-04: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-01 | `111122223333` | `i-0a200000000000005` | app-05: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-01 | `111122223333` | `i-0a200000000000006` | app-06: m5.2xlarge to m5.xlarge (max CPU 17%, max memory 34%) | $280.32 | $140.16 | $140.16 |
| SAV-02 | `111122223333` | `orders-db` | db.r5.4xlarge Multi-AZ to db.r5.2xlarge Multi-AZ | $3,150.00 | $1,690.00 | $1,460.00 |
| SAV-03 | `444455556666` | `orders-db-stg` | db.r5.2xlarge Multi-AZ to db.r5.large Single-AZ | $1,575.00 | $240.00 | $1,335.00 |
| SAV-04 | `444455556666` | `i-0b100000000000001` | stg-app-01 (m5.2xlarge) | $280.32 | $99.84 | $180.48 |
| SAV-04 | `444455556666` | `i-0b100000000000002` | stg-app-02 (m5.2xlarge) | $280.32 | $99.84 | $180.48 |
| SAV-04 | `444455556666` | `i-0b100000000000003` | stg-app-03 (m5.2xlarge) | $280.32 | $99.84 | $180.48 |
| SAV-04 | `444455556666` | `i-0b100000000000004` | stg-app-04 (m5.2xlarge) | $280.32 | $99.84 | $180.48 |

The remaining fleets have approximately appropriate capacity; the table shows the first instance
in each. Load tests drive staging CPU to 65%, supporting its current instance size.

| Resource | Current type | Compute Optimizer finding | Max CPU | Max memory |
| --- | --- | --- | ---: | ---: |
| web-01 | m5.xlarge | Optimized | 41% | 58% |
| batch-01 | c5.4xlarge | Optimized | 88% | 61% |
| stg-app-01 | m5.2xlarge | Optimized | 65% | 48% |
| ci-runner-01 | c5.xlarge | Optimized | 92% | 40% |

## 7. Savings Plans and Reserved Instances

CUR line types establish the following coverage for M3:

| Measure | Value |
| --- | ---: |
| Savings Plans eligible on-demand spend (M3) | $6,319.89 |
| Covered by the existing Compute Savings Plan | $560.64 |
| Savings Plans coverage | 8.9% |
| Existing plan utilization | 100.0% |
| Observed Savings Plan discount (1 - fee / covered) | 27.1% |
| RDS instance-hour spend (M3) | $4,745.00 |
| RDS Reserved Instance coverage | 0.0% |

The existing Compute Savings Plan is fully utilized and applies exclusively to the storefront
web fleet, giving Harbor Goods 8.9% coverage. The next plan's sizing uses the observed
27.1% discount because it reflects the instance families Harbor Goods runs.

For the proposed Compute Savings Plan (SAV-15), sizing follows these criteria:

- Include only instances that ran continuously throughout all three billing periods, using their
  capacity after rightsizing. Exclude scheduled, idle and untagged instances from this baseline.
- Set the commitment at 80% of baseline usage, leaving room for additional
  rightsizing or migration to Graviton or containers.
- Round down the hourly commitment to a valid purchase increment.

| Step | Value |
| --- | ---: |
| Steady post-change baseline (14 instances, on-demand per hour) | $4.1192 |
| Target covered on-demand per hour | $3.2954 |
| Commitment per hour (rounded down) | $2.4020 |
| On-demand equivalent covered per hour | $3.2942 |
| Commitment per month | $1,753.46 |
| Estimated saving per month | $651.29 |

EC2 changes reduce eligible monthly on-demand spending to $4,635.54. Together, the
existing and proposed plans would cover 64.0% of that spending.

The following instances form the baseline:

| Account | Instance | Sized as | On-demand per hour |
| --- | --- | --- | ---: |
| `111122223333` | `i-0a200000000000001` | m5.xlarge | $0.1920 |
| `111122223333` | `i-0a200000000000002` | m5.xlarge | $0.1920 |
| `111122223333` | `i-0a200000000000003` | m5.xlarge | $0.1920 |
| `111122223333` | `i-0a200000000000004` | m5.xlarge | $0.1920 |
| `111122223333` | `i-0a300000000000001` | c5.4xlarge | $0.6800 |
| `111122223333` | `i-0a300000000000002` | c5.4xlarge | $0.6800 |
| `111122223333` | `i-0a300000000000003` | c5.4xlarge | $0.6800 |
| `111122223333` | `i-0a300000000000004` | c5.4xlarge | $0.6800 |
| `111122223333` | `i-0a400000000000001` | t3.medium | $0.0416 |
| `123456789012` | `i-0c100000000000001` | c5.xlarge | $0.1700 |
| `123456789012` | `i-0c100000000000002` | c5.xlarge | $0.1700 |
| `123456789012` | `i-0c200000000000001` | t3.large | $0.0832 |
| `123456789012` | `i-0c200000000000002` | t3.large | $0.0832 |
| `123456789012` | `i-0c200000000000003` | t3.large | $0.0832 |

**RDS Reserved Instances (SAV-16).** Current RDS coverage stands at
0.0%. Once orders-db has been resized, reserve both production databases under
one-year terms with no upfront payment. A 30% discount supplies the planning
estimate; verify the actual rate through the Price List API before purchase. RDS MySQL Reserved
Instances support size flexibility within an instance family. Purchasing after resizing still
aligns the commitment with the running resources.

| ID | Account | Resource | Detail | Current/mo | Target/mo | Saving/mo |
| --- | --- | --- | --- | ---: | ---: | ---: |
| SAV-16 | `111122223333` | `orders-db` | db.r5.2xlarge Multi-AZ | $1,460.00 | $1,022.00 | $438.00 |
| SAV-16 | `111122223333` | `reporting-db` | db.r5.xlarge Single-AZ | $365.00 | $255.50 | $109.50 |

This audit models both commitments without purchasing either. Harbor Goods retains responsibility
for the decision and purchase.

## 8. Storage, logs and network

| ID | Account | Resource | Detail | Current/mo | Target/mo | Saving/mo |
| --- | --- | --- | --- | ---: | ---: | ---: |
| SAV-11 | `111122223333` | `/harbor-goods/order-api` | application, never expires to 30 days, 9,000 GB stored to 360 GB | $270.00 | $10.80 | $259.20 |
| SAV-11 | `111122223333` | `/harbor-goods/storefront` | application, never expires to 30 days, 3,600 GB stored to 90 GB | $108.00 | $2.70 | $105.30 |
| SAV-11 | `111122223333` | `/harbor-goods/vpc-flow` | network, never expires to 180 days, 4,800 GB stored to 720 GB | $144.00 | $21.60 | $122.40 |
| SAV-11 | `444455556666` | `/harbor-goods/order-api-stg` | application, never expires to 30 days, 1,800 GB stored to 45 GB | $54.00 | $1.35 | $52.65 |
| SAV-12 | `111122223333` | `/harbor-goods/order-api` | 1,200 GB a month ingested, 60% assumed DEBUG | $600.00 | $240.00 | $360.00 |
| SAV-13 | `123456789012` | `harbor-goods-app-logs` | 20,000 GB in 40,000,000 objects older than 30 days | $460.00 | $80.00 | $380.00 |
| SAV-13 | | | Less retrieval fees for 50 GB of reads a month | | | -$1.50 |
| SAV-14 | `444455556666` | `nat-0b1000000000000002` | stg-nat-b hourly charge | $32.85 | $0.00 | $32.85 |
| SAV-14 | `444455556666` | `nat-0b1000000000000003` | stg-nat-c hourly charge | $32.85 | $0.00 | $32.85 |
| SAV-14 | | | Less cross-AZ transfer for 40 GB moved to the remaining gateway | | | -$0.80 |

- **CloudWatch Logs retention (SAV-11).** No expiration applies to
  4 log groups. The calculation assumes stored volume stabilizes at monthly
  ingest multiplied by 0.30 and retention months, with the ratio representing compression.
  Set application log retention to 30 days and VPC flow log retention to
  180 days, first exporting any data subject to a compliance hold to S3.
- **DEBUG logging (SAV-12).** The calculation assumes DEBUG entries make up about
  60% of order-api log volume. Validate that share through a CloudWatch Logs Insights
  query before release. Excluding the storage impact keeps the savings estimate conservative.
- **S3 lifecycle (SAV-13).** Transition log objects after 30 days to
  S3 Glacier Instant Retrieval, preserving millisecond read access. Estimated savings deduct the
  cost of 50 GB in monthly reads. A one-time transition-request expense of
  $800.00 pays back over 2.1 months.
- **gp2 to gp3 (SAV-06).** Convert 18 attached gp2 volumes online.
  All are at or below 1,000 GiB, so the included gp3 capacity of 3,000 IOPS meets or exceeds their
  gp2 baseline. Volumes larger than 170 GiB receive additional provisioned throughput to preserve
  gp2's 250 MiB/s; the calculation includes that expense. Exclude unattached volumes and volumes
  belonging to idle instances, since those are scheduled for deletion.
- **Staging NAT gateways (SAV-14).** Each of the 3 staging
  gateways handles no more than 20 GB monthly. A single gateway can handle the workload;
  estimated savings account for the additional cross-AZ transfer cost.

## 9. Tagging and cost allocation

| Required tag | Share of M3 cost tagged | Untagged cost |
| --- | ---: | ---: |
| `application` | 89.2% | $2,494.25 |
| `environment` | 87.8% | $2,809.61 |
| `cost-center` | 78.1% | $5,044.25 |

Spending without tags in M3 has three components. Resources account for
$1,185.45, which resource tagging can address. Account-level data transfer
accounts for $900.00, while Savings Plan fees account for
$408.80. Those last two components cannot carry resource tags and require
allocation rules.

The highest-cost resources without tags appear below:

| Account | Service | Resource | M3 cost |
| --- | --- | --- | ---: |
| `444455556666` | Amazon EC2 (instances, EBS, NAT) | `i-0b200000000000001` | $248.20 |
| `123456789012` | Amazon EC2 (instances, EBS, NAT) | `vol-0c9000000000000e1` | $160.00 |
| `444455556666` | Amazon CloudWatch | `/harbor-goods/order-api-stg` | $129.00 |
| `111122223333` | Amazon EC2 (instances, EBS, NAT) | `vol-0a9000000000000e1` | $100.00 |
| `123456789012` | Amazon EC2 (instances, EBS, NAT) | `i-0c200000000000004` | $60.74 |
| `123456789012` | Amazon EC2 (instances, EBS, NAT) | `i-0c200000000000005` | $60.74 |
| `111122223333` | Amazon EC2 (instances, EBS, NAT) | `vol-0a9000000000000e2` | $50.00 |
| `444455556666` | Amazon EC2 (instances, EBS, NAT) | `vol-0b200000000000001` | $50.00 |

The recommended allocation controls are:

1. **Require three tags**: `application`, `environment` and `cost-center`. Publish permitted values
   in a single location, and retain `Name` for human identification rather than cost allocation.
2. **Apply creation-time controls**: use an AWS Organizations tag policy to govern allowed values.
   Separately, require tags in Terraform modules. An AWS Config `required-tags` rule reports drift.
3. **Enable cost allocation for all three keys** in the management account, making them available
   in Cost Explorer and the CUR.
4. **Use AWS Cost Categories for costs without resource tags**: apportion account-level data
   transfer according to each application's share of CloudFront and ELB usage. Allocate the
   Savings Plan fee according to each cost center's covered usage.
5. **Assign responsibility for unowned resources**: give every resource above an owner or deletion
   date during the first quick-win window. The list already includes the idle instances
   (SAV-10).
6. **Produce monthly showback reports** for each cost center and target 95% tagged spend.

## 10. Assumptions

`data/assumptions.json` holds all assumptions. Updating a value and running `make evidence`
recalculates its impact throughout the report.

| Assumption | Value | Used by |
| --- | ---: | --- |
| Hours in a month | 730 | all |
| Staging schedule | 12 h x 5 days = 260 h/month | SAV-04 |
| Snapshot age threshold | 180 days | SAV-07 |
| Rollback snapshot kept for | 1 month | SAV-05 |
| Compute Savings Plan coverage target | 80% of the steady baseline | SAV-15 |
| Compute Savings Plan discount | 27.1% (observed) | SAV-15 |
| RDS Reserved Instance discount | 30% (planning figure) | SAV-16 |
| CloudWatch Logs stored-to-ingested ratio | 0.30 | SAV-11 |
| Retention: application / network logs | 30 days / 180 days | SAV-11 |
| DEBUG share of order-api log volume | 60% | SAV-12 |
| S3 transition age | 30 days | SAV-13 |
| Expected Glacier Instant Retrieval reads | 50 GB/month | SAV-13 |
| Staging NAT gateways kept | 1 | SAV-14 |

That file also contains unit prices approximating us-east-1 on-demand list pricing. Because
Savings Plan and Reserved Instance rates vary, verify them through the AWS Price List API before
making any purchase.

## 11. Reproduce this report

```sh
make verify     # tests, evidence and report freshness, PDF freshness, lint
make evidence   # regenerate evidence/ and this report from data/
```

The referenced evidence resides in `evidence/`, including `spend-by-service.csv`,
`spend-by-account.csv`, `savings-ranked.csv`, `savings-detail.csv`, `tag-coverage.csv`,
`commitments.json` and `facts.json`. Checks in `tests/` independently recalculate every figure
from `data/` and fail when report contents diverge from those inputs.

---

*Fictional sample: This report uses an invented company, Harbor Goods, and entirely synthetic data.
All savings figures are estimates rather than measured outcomes.*
