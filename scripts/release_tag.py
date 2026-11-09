#!/usr/bin/env python3
"""Resolve the tag for a merged ``Release vX.Y.Z`` PR and verify version pins.

Used by ``.github/workflows/release-tag.yaml``. Writes ``tag=<vX.Y.Z>`` (or an
empty ``tag=`` for a non-release PR) to ``--github-output``. Exits 1 without
writing when any pinned install doc disagrees with the title, so a release
whose bump commit was skipped never gets tagged.
"""

import argparse
from pathlib import Path
import re
import sys

PINNED = ("README.md", "README.zh-TW.md", "docs/install-quickstart.md")
TITLE_RE = re.compile(r"Release (v\d+\.\d+\.\d+)")
PIN_RE = re.compile(r"^RELEASE=(\S+)", re.MULTILINE)


def tag_for_title(title):
    match = TITLE_RE.fullmatch(title.strip())
    return match.group(1) if match else None


def pinned_tag(path):
    if not path.is_file():
        return None
    match = PIN_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def stale_pins(root, tag):
    return [rel for rel in PINNED if pinned_tag(root / rel) != tag]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)

    tag = tag_for_title(args.title)
    if not tag and args.title.strip().startswith("Release v"):
        print(f"::error::release PR title must be exactly 'Release vX.Y.Z', got {args.title!r}",
              file=sys.stderr)
        return 1
    if tag:
        stale = stale_pins(args.root, tag)
        if stale:
            for rel in stale:
                found = pinned_tag(args.root / rel) or "no RELEASE= pin"
                print(f"::error file={rel}::expected RELEASE={tag}, found {found}",
                      file=sys.stderr)
            return 1
    with args.github_output.open("a", encoding="utf-8") as fh:
        fh.write(f"tag={tag or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
