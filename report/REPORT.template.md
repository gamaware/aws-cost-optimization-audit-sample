# Harbor Goods: AWS cost optimization audit

<!-- `make evidence` generates this file from report/REPORT.template.md. Make edits in the template. -->

> **Fictional sample.** Harbor Goods is an invented retailer. This repository uses synthetic billing
> records, recommendations and inventories; all savings figures estimate outcomes from those
> fictional inputs. The report represents neither an actual company nor measured results.

| Item | Value |
| --- | --- |
| Client | Harbor Goods (fictional mid-size retailer) |
| Scope | {{account_count}} AWS accounts in one AWS Organization, region `us-east-1` |
| Billing window | {{first_period}} to {{period}} (three monthly billing periods, oldest first) |
| Analysis period | {{period}}, net unblended cost {{bill}} |
| Access used | Read-only exports; no change was made to any account |
| Deliverable | This report, `evidence/` and the scripts that produced both |

## 1. Executive summary

AWS spending for Harbor Goods reached {{bill}} in {{period}}, an increase of
{{bill_growth_pct}} ({{bill_growth}}) from {{first_period}}. Across {{finding_count}} opportunities,
the audit estimates savings of **{{savings_monthly}} a month ({{savings_annual}} a year)**,
equivalent to {{savings_pct}} of the {{period}} bill. Completing every recommendation would bring
monthly costs for the same workload to approximately {{bill_after}}.

- **{{quick_count}} quick wins** offer {{quick_monthly}} in monthly savings at low effort and low
  risk. Most involve removing idle resources or changing a single setting; a platform engineer can
  complete these within a week.
- **{{planned_count}} planned items** offer {{planned_monthly}} in monthly savings. Each requires
  a load test, release or one-year commitment and therefore needs a change ticket and rollback plan.
- One-time expenses of {{one_time_total}} cover rollback snapshots for volume deletions and S3
  lifecycle transition requests. Each expense pays back within a few months.

The largest three opportunities account for these estimated monthly savings:

1. **{{top1.id}}: {{top1.title}}** reduces monthly costs by {{top1.monthly}}.
2. **{{top2.id}}: {{top2.title}}** reduces monthly costs by {{top2.monthly}}.
3. **{{top3.id}}: {{top3.title}}** reduces monthly costs by {{top3.monthly}}.

Incomplete tagging also limits cost allocation: `cost-center` appears on only {{tag.cost-center}}
of spending in {{period}}. Finance therefore cannot yet provide individual team bills.
Section 9 describes the corrective work.

## 2. Scope and method

Only exports inform this audit, matching the files a client would supply through read-only access:

- **Cost and Usage Report (CUR 2.0 columns)**: `data/synthetic/cur/` contains {{line_count}} line
  items covering {{service_count}} services, aggregated by resource and billing period.
- **AWS Compute Optimizer**: recommendations for EC2 and RDS based on a 14-day look-back.
- **AWS Trusted Advisor**: cost-optimization checks identifying idle and unattached resources.
- **Inventories**: records of EBS snapshots, AMIs, CloudWatch log groups, NAT gateways and the
  existing Savings Plan, plus the log bucket's S3 storage-by-age report.

The calculations follow these rules:

1. The CUR for {{period}} supplies every current cost. Recommendation tools identify candidate
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

{{table:services}}

Spending increased {{bill_growth}} across the billing window, with the largest changes in:

- {{mover1}}, which rose {{mover1.delta}} as the production order-api fleet expanded from
  {{app_count_first}} to {{app_count_last}} instances and staging expanded from
  {{stg_count_first}} to {{stg_count_last}}.
- {{mover2}}, which rose {{mover2.delta}} as log groups without expiration continued accumulating
  data each month.
- {{mover3}}, which rose {{mover3.delta}} alongside monthly increases in production internet egress.

The account breakdown follows:

{{table:accounts}}

## 4. Ranked savings

The following ranking orders recommendations by estimated monthly savings from fictional data.
Recommendation IDs remain unchanged when ranks move. `evidence/savings-detail.csv` provides the
calculations for individual resources.

{{table:ranked}}

## 5. Quick wins versus planned work

**Quick wins: {{quick_monthly}} monthly ({{quick_annual}} annually).** Complete these before planned
work, following rank order within a single change window. Every item either supports a direct
reversal or retains a snapshot until validation confirms the change.

{{table:quick}}

**Planned work: {{planned_monthly}} monthly ({{planned_annual}} annually).** Follow this order:

1. Complete rightsizing ({{rightsize-rds-prod.id}}, {{rightsize-ec2.id}}) before purchasing
   commitments. Each resize requires a load test and maintenance window, with a return to the
   previous instance class available for rollback.
2. Purchase commitments ({{compute-savings-plan.id}}, {{rds-reserved-instances.id}}) against the
   resulting usage. An earlier purchase would commit to the oversized fleet for one year.
3. Include the logging update ({{debug-logging.id}}) in the next order-api release. Implement
   staging NAT gateway consolidation ({{nat-consolidation.id}}) through the staging network code.

{{table:planned}}

## 6. Idle, unattached and rightsizing findings

### 6.1 Idle and unattached resources

These resources come from Trusted Advisor findings. Snapshot selection applies an additional
rule: snapshots must exceed {{snapshot_days}} days in age, have no AMI reference and carry no
`retention` tag. This excludes {{snapshots_held}} legal-hold snapshot and {{snapshots_in_ami}}
snapshots backing AMIs.

{{table:idle}}

Create a snapshot of every one of the {{unattached-ebs.count}} unattached volumes before deletion,
then retain those snapshots for one month. The one-time cost is {{unattached-ebs.one_time}},
an upper bound assuming full volume size, with payback in {{unattached-ebs.payback_months}} months.

### 6.2 Rightsizing and scheduling

Compute Optimizer classified both orders databases and the order-api instances as
over-provisioned. Because staging order-api instances handle working-day activity, the
recommendation schedules {{scheduled_hours}} running hours per month while retaining their
current instance type.

{{table:rightsizing}}

The remaining fleets have approximately appropriate capacity; the table shows the first instance
in each. Load tests drive staging CPU to {{stg_cpu_max}}, supporting its current instance size.

{{table:optimized}}

## 7. Savings Plans and Reserved Instances

CUR line types establish the following coverage for {{period}}:

{{table:coverage}}

The existing Compute Savings Plan is fully utilized and applies exclusively to the storefront
web fleet, giving Harbor Goods {{sp_coverage}} coverage. The next plan's sizing uses the observed
{{sp_discount}} discount because it reflects the instance families Harbor Goods runs.

For the proposed Compute Savings Plan ({{compute-savings-plan.id}}), sizing follows these criteria:

- Include only instances that ran continuously throughout all three billing periods, using their
  capacity after rightsizing. Exclude scheduled, idle and untagged instances from this baseline.
- Set the commitment at {{sp_target_share}} of baseline usage, leaving room for additional
  rightsizing or migration to Graviton or containers.
- Round down the hourly commitment to a valid purchase increment.

{{table:sp_sizing}}

EC2 changes reduce eligible monthly on-demand spending to {{sp_eligible_after}}. Together, the
existing and proposed plans would cover {{sp_coverage_after}} of that spending.

The following instances form the baseline:

{{table:sp_baseline}}

**RDS Reserved Instances ({{rds-reserved-instances.id}}).** Current RDS coverage stands at
{{rds_coverage}}. Once orders-db has been resized, reserve both production databases under
one-year terms with no upfront payment. A {{rds_ri_discount}} discount supplies the planning
estimate; verify the actual rate through the Price List API before purchase. Aurora PostgreSQL
Reserved Instances support size flexibility within an instance family. Purchasing after resizing still
aligns the commitment with the running resources.

{{table:ri}}

This audit models both commitments without purchasing either. Harbor Goods retains responsibility
for the decision and purchase.

## 8. Storage, logs and network

{{table:storage}}

- **CloudWatch Logs retention ({{log-retention.id}}).** No expiration applies to
  {{log-retention.count}} log groups. The calculation assumes stored volume stabilizes at monthly
  ingest multiplied by {{log_ratio}} and retention months, with the ratio representing compression.
  Set application log retention to {{retention_application}} days and VPC flow log retention to
  {{retention_network}} days, first exporting any data subject to a compliance hold to S3.
- **DEBUG logging ({{debug-logging.id}}).** The calculation assumes DEBUG entries make up about
  {{debug_share}} of order-api log volume. Validate that share through a CloudWatch Logs Insights
  query before release. Excluding the storage impact keeps the savings estimate conservative.
- **S3 lifecycle ({{s3-lifecycle.id}}).** Transition log objects after {{s3_after_days}} days to
  S3 Glacier Instant Retrieval, preserving millisecond read access. Estimated savings deduct the
  cost of {{s3_retrieval_gb}} GB in monthly reads. A one-time transition-request expense of
  {{s3-lifecycle.one_time}} pays back over {{s3-lifecycle.payback_months}} months.
- **gp2 to gp3 ({{gp2-to-gp3.id}}).** Convert {{gp2-to-gp3.count}} attached gp2 volumes online.
  All are at or below 1,000 GiB, so the included gp3 capacity of 3,000 IOPS meets or exceeds their
  gp2 baseline. Volumes larger than 170 GiB receive additional provisioned throughput to preserve
  gp2's 250 MiB/s; the calculation includes that expense. Exclude unattached volumes and volumes
  belonging to idle instances, since those are scheduled for deletion.
- **Staging NAT gateways ({{nat-consolidation.id}}).** Each of the {{stg_nat_count}} staging
  gateways handles no more than {{stg_nat_gb}} GB monthly. A single gateway can handle the workload;
  estimated savings account for the additional cross-AZ transfer cost.

## 9. Tagging and cost allocation

{{table:tags}}

Spending without tags in {{period}} has three components. Resources account for
{{untagged.untagged_resources}}, which resource tagging can address. Account-level data transfer
accounts for {{untagged.shared_data_transfer}}, while Savings Plan fees account for
{{untagged.commitment_fees}}. Those last two components cannot carry resource tags and require
allocation rules.

The highest-cost resources without tags appear below:

{{table:untagged}}

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
   ({{idle-instances.id}}).
6. **Produce monthly showback reports** for each cost center and target 95% tagged spend.

## 10. Assumptions

`data/assumptions.json` holds all assumptions. Updating a value and running `make evidence`
recalculates its impact throughout the report.

{{table:assumptions}}

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
