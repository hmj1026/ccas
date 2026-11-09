#!/usr/bin/env python3
"""Resolve the tag for a merged ``Release vX.Y.Z`` PR and verify version pins.

Used by ``.github/workflows/release-tag.yaml``. Writes ``tag=<vX.Y.Z>`` (or an
empty ``tag=`` for a non-release PR) to ``--github-output``. Exits 1 without
writing when any entry in ``PINS`` disagrees with the title, so a release whose
bump commit was incomplete never gets tagged. ``bump_version.py`` rewrites the
same ``PINS``, so what CI checks is exactly what the bump changes.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

SEMVER = r"(\d+\.\d+\.\d+)"
TITLE_RE = re.compile(rf"Release v{SEMVER}")


@dataclass(frozen=True)
class Pin:
    path: str
    name: str
    pattern: re.Pattern

    @property
    def label(self):
        return f"{self.path} ({self.name})"


def _pin(path, name, regex):
    return Pin(path, name, re.compile(regex.replace("{V}", SEMVER), re.MULTILINE))


# Mechanical version locations. Group 1 is the bare X.Y.Z; each must match once.
PINS = (
    _pin("README.md", "RELEASE", r"^RELEASE=v{V}\b"),
    _pin("README.zh-TW.md", "RELEASE", r"^RELEASE=v{V}\b"),
    _pin("docs/install-quickstart.md", "RELEASE", r"^RELEASE=v{V}\b"),
    _pin("docs/install-quickstart.md", "CCAS_VERSION example", r"與 release tag 一致（例：`v{V}`"),
    _pin("docs/upgrade-guide.md", "CCAS_VERSION sed", r"CCAS_VERSION=v{V}/' \.env"),
    _pin("docs/upgrade-guide.md", "git checkout", r"^git checkout v{V} +# 改成目標 tag"),
    _pin("docs/mcp-installation.md", "release metadata", r"目前為 v{V}"),
    _pin("backend/src/ccas/__init__.py", "__version__", r'^__version__ = "{V}"'),
    _pin("backend/tests/unit/test_version_metadata.py", "version assertion",
         r'assert __version__ == "{V}"'),
)


def tag_for_title(title):
    match = TITLE_RE.fullmatch(title.strip())
    return f"v{match.group(1)}" if match else None


def pin_matches(root, pin):
    path = root / pin.path
    if not path.is_file():
        return []
    return list(pin.pattern.finditer(path.read_text(encoding="utf-8")))


def read_pins(root):
    """Map each pin label to its version, or None when it is absent or ambiguous."""
    versions = {}
    for pin in PINS:
        matches = pin_matches(root, pin)
        versions[pin.label] = matches[0].group(1) if len(matches) == 1 else None
    return versions


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
        found = read_pins(args.root)
        stale = [label for label, version in found.items() if f"v{version}" != tag]
        if stale:
            for label in stale:
                print(f"::error::{label}: expected {tag}, found "
                      f"{found[label] or 'missing or duplicated pin'}", file=sys.stderr)
            return 1
    with args.github_output.open("a", encoding="utf-8") as fh:
        fh.write(f"tag={tag or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
