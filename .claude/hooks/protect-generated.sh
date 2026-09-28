#!/usr/bin/env bash
# PreToolUse hook: block hand edits to generated files. Exit 2 blocks the edit.
set -euo pipefail

# Fail closed: without jq the hook cannot read the path, so block rather than allow.
command -v jq > /dev/null 2>&1 || {
    echo "protect-generated: jq is required" >&2
    exit 2
}
file="$(jq -r '.tool_input.file_path // empty')"
case "$file" in
    data/synthetic/* | */data/synthetic/* | evidence/* | */evidence/* | \
        report/REPORT.md | */report/REPORT.md | report/REPORT.pdf | */report/REPORT.pdf)
        echo "$file is generated. Edit scripts/, data/assumptions.json or report/REPORT.template.md," \
            "then run 'make data' or 'make evidence'." >&2
        exit 2
        ;;
esac
exit 0
