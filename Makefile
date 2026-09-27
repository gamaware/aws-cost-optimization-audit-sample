# Every target except test-live runs offline: no AWS account, no credentials.
# CI calls `make verify`, so a green local run means a green pipeline.

UV ?= uv
RUN := $(UV) run --frozen
PY := PYTHONPATH=scripts $(RUN) python

.PHONY: verify lint test check data evidence pdf summary test-live clean

## verify: everything CI runs (lint, tests, output freshness)
verify: lint test check

## lint: ruff lint and format checks on scripts and tests
lint:
	$(RUN) ruff check scripts tests
	$(RUN) ruff format --check scripts tests

## test: recompute every figure from data/ and compare with the report
test:
	$(RUN) pytest

## check: fail if data/, evidence/, REPORT.md or REPORT.pdf are stale
check:
	$(RUN) python scripts/generate_synthetic.py --check
	$(PY) -m costaudit check
	$(RUN) python scripts/build_pdf.py --check

## data: regenerate the synthetic exports in data/synthetic/
data:
	$(RUN) python scripts/generate_synthetic.py

## evidence: regenerate evidence/, report/REPORT.md and report/REPORT.pdf (needs Docker)
evidence:
	$(PY) -m costaudit build
	$(MAKE) pdf

## pdf: render report/REPORT.pdf from report/REPORT.md (needs Docker)
pdf:
	$(RUN) python scripts/build_pdf.py

## summary: print the ranked savings list
summary:
	$(PY) -m costaudit summary

## test-live: read-only smoke test of the exporters against the dev account (manual, never in CI)
test-live:
	./scripts/test_live.sh

clean:
	rm -rf .pytest_cache .ruff_cache
