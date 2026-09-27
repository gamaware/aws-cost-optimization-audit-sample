#!/usr/bin/env bash
# PostToolUse hook: format the edited file. Never fails the edit.
set -euo pipefail

file="$(jq -r '.tool_input.file_path // empty')"
[ -f "$file" ] || exit 0
case "$file" in
    *.sh)
        if command -v shellharden > /dev/null 2>&1; then
            shellharden --replace "$file" 2> /dev/null || true
        fi
        chmod +x "$file"
        ;;
    *.md)
        if command -v markdownlint > /dev/null 2>&1; then
            markdownlint --fix "$file" 2> /dev/null || true
        fi
        ;;
    *.py)
        if command -v uv > /dev/null 2>&1; then
            uv run --frozen ruff format "$file" > /dev/null 2>&1 || true
        fi
        ;;
esac
exit 0
