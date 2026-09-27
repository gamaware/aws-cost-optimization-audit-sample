#!/usr/bin/env bash
# Read-only live smoke test: confirm that the real exporters still return the fields the
# offline audit reads. Manual only, never in CI. See README "Verify locally".
#
# - Uses the maintainer's `dev` profile and prints the caller identity first.
# - Creates no AWS resources. Output goes to a temporary directory that is deleted on exit
#   and is never committed.
# - Ends by confirming that nothing tagged purpose=portfolio-test exists in the account.
# - Cost Explorer charges USD 0.01 per API request; this script makes one.
set -euo pipefail

PROFILE="${AWS_PROFILE_LIVE:-dev}"
REGION="${AWS_REGION_LIVE:-us-east-1}"
TAG_KEY="purpose"
TAG_VALUE="portfolio-test"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

aws_ro() {
    aws --profile "$PROFILE" --region "$REGION" --output json "$@"
}

echo "== caller identity (confirm this is the dev account before continuing)"
aws_ro sts get-caller-identity

# Last complete calendar month, computed at run time.
start="$(date -u -v1d -v-1m +%Y-%m-01 2> /dev/null || date -u -d "$(date -u +%Y-%m-01) -1 month" +%Y-%m-01)"
end="$(date -u +%Y-%m-01)"

echo "== Cost Explorer: spend by service, $start to $end"
aws_ro ce get-cost-and-usage --time-period "Start=$start,End=$end" --granularity MONTHLY \
    --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE > "$workdir/ce.json"

echo "== Compute Optimizer: EC2 recommendations (first page)"
if aws_ro compute-optimizer get-ec2-instance-recommendations --max-results 5 > "$workdir/co.json" 2> "$workdir/co.err"; then
    :
else
    echo "Compute Optimizer is not enabled or not reachable; skipping its shape check:"
    cat "$workdir/co.err"
    echo '{"instanceRecommendations": []}' > "$workdir/co.json"
fi

echo "== shape checks"
python3 - "$workdir/ce.json" "$workdir/co.json" <<'PY'
import json
import sys

ce = json.load(open(sys.argv[1]))
groups = ce["ResultsByTime"][0]["Groups"]
assert all("UnblendedCost" in g["Metrics"] for g in groups), "Cost Explorer groups lack UnblendedCost"
print(f"Cost Explorer: {len(groups)} services returned with UnblendedCost")

co = json.load(open(sys.argv[2]))
needed = {"instanceArn", "currentInstanceType", "finding", "utilizationMetrics", "recommendationOptions"}
for rec in co["instanceRecommendations"]:
    missing = needed - rec.keys()
    assert not missing, f"Compute Optimizer record lacks {missing}"
print(f"Compute Optimizer: {len(co['instanceRecommendations'])} records carry the fields the audit reads")
PY

echo "== leftover check: resources tagged $TAG_KEY=$TAG_VALUE"
leftovers="$(aws_ro resourcegroupstaggingapi get-resources \
    --tag-filters "Key=$TAG_KEY,Values=$TAG_VALUE" --query 'length(ResourceTagMappingList)')"
if [ "$leftovers" != "0" ]; then
    echo "found $leftovers resource(s) tagged $TAG_KEY=$TAG_VALUE; clean them up" >&2
    exit 1
fi
echo "no tagged leftovers; live smoke test passed"
