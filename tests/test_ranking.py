"""Ranking, classification and totals follow the rules stated in the report."""

from decimal import Decimal

from costaudit.analysis import Audit

# A resource may appear in two findings only when they price different cost components.
# order-api logs: retention cuts storage, the DEBUG change cuts ingestion.
ALLOWED_OVERLAP = {"/harbor-goods/order-api"}


def test_ranked_by_monthly_saving(audit: Audit):
    values = [r.finding.monthly for r in audit.ranked]
    assert values == sorted(values, reverse=True)
    assert [r.rank for r in audit.ranked] == list(range(1, len(audit.ranked) + 1))


def test_ids_are_stable_and_unique(audit: Audit):
    ids = [r.fid for r in audit.ranked]
    assert len(set(ids)) == len(ids) == 16
    assert audit.by_key("rightsize-ec2").fid == "SAV-01"
    assert audit.by_key("rds-reserved-instances").fid == "SAV-16"


def test_quick_win_rule(audit: Audit):
    for r in audit.ranked:
        assert (r.kind == "Quick win") == (r.effort == "Low" and r.risk == "Low")


def test_every_finding_has_a_rating_with_a_reason(audit: Audit):
    ratings = audit.ds.assumptions["ratings"]
    assert set(ratings) == {r.finding.key for r in audit.ranked}
    assert all(
        v["effort"] in {"Low", "Medium", "High"} and v["risk"] in {"Low", "Medium", "High"} and v["why"]
        for v in ratings.values()
    )


def test_totals_add_up(audit: Audit):
    assert audit.monthly_total == audit.monthly_of("Quick win") + audit.monthly_of("Planned work")
    assert audit.monthly_total == Decimal("8134.97")
    for r in audit.ranked:
        assert r.finding.annual == r.finding.monthly * 12
        assert r.finding.monthly > 0
        for d in r.finding.details:
            assert d.current > 0 and d.saving > 0, (r.fid, d.resource)


def test_no_resource_counted_twice(audit: Audit):
    seen: dict[str, str] = {}
    for r in audit.ranked:
        if r.finding.group == "commitment":
            continue  # commitments price the post-change usage, checked in test_numbers
        for res in r.finding.resources:
            assert res not in seen or res in ALLOWED_OVERLAP, f"{res} in {seen.get(res)} and {r.fid}"
            seen[res] = r.fid


def test_commitment_baseline_excludes_changed_and_untagged_instances(audit: Audit):
    baseline = {d.resource for d in audit.sizing.baseline_rows}
    for key in ("schedule-staging", "idle-instances"):
        assert not baseline & set(audit.by_key(key).finding.resources)
    untagged = {ln.resource for ln in audit.ds.current() if not ln.tag("application")}
    assert not baseline & untagged
    # app-05 and app-06 started in M2, so they are not part of the steady baseline.
    assert not baseline & {"i-0a200000000000005", "i-0a200000000000006"}


def test_savings_are_a_plausible_share_of_the_bill(audit: Audit):
    from costaudit import analysis

    share = audit.monthly_total / analysis.totals(audit.ds)["M3"]
    assert Decimal("0.10") < share < Decimal("0.45")
