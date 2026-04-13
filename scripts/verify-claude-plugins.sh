#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PIN_FILE="$REPO_ROOT/.claude/plugin-pins.json"

if [ -z "${HOME:-}" ]; then
    echo "ERROR: \$HOME not set" >&2
    exit 2
fi

MARKETPLACES_DIR="$HOME/.claude/plugins/marketplaces"

if [ ! -f "$PIN_FILE" ]; then
    echo "ERROR: $PIN_FILE not found" >&2
    exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required for plugin pin verification" >&2
    exit 2
fi

if [ ! -d "$MARKETPLACES_DIR" ]; then
    echo "-> Claude plugins not installed locally; skipping pin verification"
    exit 0
fi

mode="${1:-verify}"
fail=0

while IFS=$'\t' read -r name expected; do
    dir="$MARKETPLACES_DIR/$name"
    if [ ! -d "$dir/.git" ]; then
        echo "WARN: marketplace '$name' not installed at $dir; skipping"
        continue
    fi
    actual="$(git -C "$dir" rev-parse HEAD)"

    if [ "$mode" = "--update" ]; then
        if [ "$actual" != "$expected" ]; then
            tmp="$(mktemp)"
            jq --arg n "$name" --arg v "$actual" \
                '.marketplaces[$n] = $v' "$PIN_FILE" > "$tmp"
            mv "$tmp" "$PIN_FILE"
            echo "-> updated pin for $name: $expected -> $actual"
        else
            echo "-> $name already at $expected"
        fi
        continue
    fi

    if [ "$actual" != "$expected" ]; then
        echo "ERROR: Claude plugin marketplace '$name' has drifted" >&2
        echo "       Expected: $expected" >&2
        echo "       Actual:   $actual" >&2
        echo "       To sync local to pin: git -C $dir fetch && git -C $dir checkout $expected" >&2
        echo "       To accept local as new pin: $0 --update && git add $PIN_FILE" >&2
        fail=1
    fi
done < <(jq -r '.marketplaces | to_entries[] | [.key, .value] | @tsv' "$PIN_FILE")

if [ "$fail" = "1" ]; then
    exit 1
fi

if [ "$mode" != "--update" ]; then
    echo "-> Claude plugin pins OK"
fi
