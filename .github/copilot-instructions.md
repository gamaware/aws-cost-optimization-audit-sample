# Copilot code review instructions

This repository is a fictional sample deliverable: an offline AWS cost audit of "Harbor Goods".

- Flag any float used for money; the scripts use `Decimal` throughout.
- Flag hand-typed dollar amounts or percentages in `report/REPORT.template.md`; figures must come
  from placeholders so the tests can reproduce them.
- Flag hand edits to generated files: `data/synthetic/`, `evidence/`, `report/REPORT.md`, `report/REPORT.pdf`.
- Flag any account ID other than the AWS documentation examples, and any real IP, ARN, email or client name.
- Flag suppressed lint rules (`noqa`, `shellcheck disable`); fix the code instead.
- Check that pull request titles follow Conventional Commits.
