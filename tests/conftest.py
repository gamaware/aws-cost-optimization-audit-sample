"""Shared fixtures: the dataset and the audit are built once per test session."""

import pytest
from costaudit import analysis, model


@pytest.fixture(scope="session")
def ds() -> model.Dataset:
    return model.load()


@pytest.fixture(scope="session")
def audit(ds: model.Dataset) -> analysis.Audit:
    return analysis.run(ds)
