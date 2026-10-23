#!/usr/bin/env python3
"""Conservative documentation-only routing and the stable CI acceptance gate."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

CODE_JOBS = (
    "backend-lint", "backend-test", "backend-integration-test",
    "frontend-lint-test", "frontend-e2e",
)
ROOT_DOCS = {"README.md", "README.zh-TW.md", "AGENTS.md", "CLAUDE.md",
             "GEMINI.md", "GLOSSARY.md"}


def classify(root, base, head):
    fallback = {"docs_only": False, "reason": "missing or unusable diff"}
    if not base or not head:
        return fallback
    result = subprocess.run(
        ["git", "diff", "--raw", "-z", "--no-renames", base, head, "--"],
        cwd=root, capture_output=True,
    )
    if result.returncode or not result.stdout:
        return fallback
    fields = result.stdout.split(b"\0")
    paths = []
    try:
        for index in range(0, len(fields) - 1, 2):
            metadata = fields[index].decode("ascii").split()
            name = fields[index + 1].decode("utf-8")
            if len(metadata) != 5 or not metadata[0].startswith(":"):
                return fallback
            modes = {metadata[0][1:], metadata[1]}
            path = PurePosixPath(name)
            if not modes <= {"000000", "100644"} or not (
                name in ROOT_DOCS or (path.parts[0] == "docs" and path.suffix == ".md")
            ):
                return {"docs_only": False, "reason": f"full checks required: {name}"}
            paths.append(name)
    except (ValueError, IndexError, UnicodeError):
        return fallback
    return {"docs_only": bool(paths), "reason": "only allowlisted Markdown changed"}


def gate(needs):
    for name in ("plan", "docs-check", "scripts-checks"):
        if needs.get(name, {}).get("result") != "success":
            return False
    selection = needs["plan"].get("outputs", {}).get("docs_only")
    if selection not in ("true", "false"):
        return False
    expected = "skipped" if selection == "true" else "success"
    return all(needs.get(name, {}).get("result") == expected for name in CODE_JOBS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()
    if args.gate:
        passed = gate(json.loads(os.environ.get("NEEDS_JSON", "{}")))
        print("CI Gate: " + ("PASS" if passed else "FAIL"))
        return 0 if passed else 1
    plan = classify(args.root, args.base, args.head)
    print(json.dumps(plan))
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"docs_only={str(plan['docs_only']).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
