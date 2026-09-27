# 0003. Size commitments last, on the steady post-change baseline

## Status

Accepted

## Context

Savings Plans and Reserved Instances save the most when they match usage that will still exist for the
whole term. An audit that sizes them on current usage and then also counts rightsizing savings counts
the same dollar twice, and it recommends a commitment for capacity that is about to be removed.

## Decision

The Compute Savings Plan is sized on instances that ran in every billing period of the trend window,
priced as they will be after rightsizing. Scheduled, idle and untagged instances are left out. The plan
commits to 80% of that baseline, rounded down to the purchase increment. The discount is the one
observed on the client's existing plan (1 - fee / on-demand equivalent covered). RDS Reserved Instances
cover production databases after the resize, at a stated planning discount.

## Consequences

- The estimate is conservative. New instances from the last two periods only join the baseline once
  they have run for a full trend window.
- The observed discount reflects the instance families Harbor Goods runs, but it comes from one plan.
  With no existing plan, the code stops with an error rather than guessing.
- The report tells the client to buy the commitments after rightsizing, not before.

## Compliance

- `tests/test_numbers.py::test_compute_savings_plan_sizing` recomputes the baseline, commitment and saving.
- `tests/test_ranking.py::test_commitment_baseline_excludes_changed_and_untagged_instances` checks the
  exclusions.
- `scripts/costaudit/commitments.py::coverage` raises if the observed discount cannot be computed.

## Notes

Alternatives considered:

- **Use the Cost Explorer purchase recommendation directly.** It looks at past usage, so it does not
  know about the rightsizing in this report.
- **Commit to 100% of the baseline.** It saves more on paper, but leaves no headroom for the next round
  of rightsizing or a move to Graviton.
