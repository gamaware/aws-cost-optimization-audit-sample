# 0001. Generate the synthetic exports from code

## Status

Accepted

## Context

The audit needs realistic inputs: a Cost and Usage Report extract, Compute Optimizer and Trusted Advisor
results, and resource inventories. Real exports cannot be published, and hand-written CSV and JSON drift
out of step with each other: a volume listed as unattached must also appear in the CUR with the same
size and cost.

## Decision

`scripts/generate_synthetic.py` builds every file in `data/synthetic/` from one resource catalog. Every
file uses AWS documentation example account IDs and RFC 5737 addresses, and the output is byte-for-byte
deterministic. Billing periods are labelled M1 to M3 instead of calendar months, which keeps the sample
dateless.

## Consequences

- Cross-file consistency comes from construction: the CUR, the recommendations and the inventories all
  come from the same catalog.
- Changing the scenario means editing Python, not data files. Reviewers read one catalog instead of
  ten exports.
- The data is plausible rather than real. Unit prices approximate us-east-1 list prices and are
  labelled as approximations.

## Compliance

- `tests/test_data.py::test_generator_reproduces_committed_files` fails if a committed file differs
  from the generator's output. `make verify` also runs `generate_synthetic.py --check`.
- `test_only_aws_documentation_account_ids` and `test_only_documentation_ip_addresses` scan `data/`.
- `test_every_flagged_resource_is_billed` ties every recommendation to a CUR line.

## Notes

Alternatives considered:

- **Hand-written fixtures.** Simpler to start with, but they drift out of step and are hard to review.
- **Anonymised real exports.** Rejected: the risk of leaking a real identifier outweighs the realism.
