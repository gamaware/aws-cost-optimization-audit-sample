# 0002. Render the report from a template with no hand-typed figures

## Status

Accepted

## Context

A cost report loses credibility the moment one figure disagrees with another, or with the data. Reports
written by hand collect such errors whenever an assumption changes late in an engagement.

## Decision

`report/REPORT.template.md` holds prose only. Every dollar amount, percentage, count and table reaches
`report/REPORT.md` through a `{{ placeholder }}` filled by `scripts/costaudit/report.py`. The same run
writes `evidence/`. Money is `Decimal` throughout. Each finding is rounded to the cent, annual figures
are twelve times the rounded monthly figure, and totals add the rounded values.

## Consequences

- Changing an assumption in `data/assumptions.json` and running `make evidence` updates every figure,
  table and ranking at once.
- Prose that describes the data, such as the order of the largest movers, still needs a test to keep
  it true.
- Editing the report means editing the template, which is less direct than editing a document.

## Compliance

- `tests/test_report.py::test_template_has_no_hand_typed_money_or_percentages` rejects literal figures
  in the template; a policy target such as the 95% tagging goal is the only allowed exception.
- `test_committed_outputs_match_a_fresh_run` fails when `REPORT.md` or `evidence/` is stale.
- `tests/test_numbers.py` recomputes each saving from first principles (hours x rate, GB x price).

## Notes

Alternatives considered:

- **A notebook.** Good for exploration, but hard to diff and review.
- **A spreadsheet.** Familiar to finance teams, but formulas are hard to review and test in a pull request.
