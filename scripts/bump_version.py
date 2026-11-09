#!/usr/bin/env python3
"""Rewrite every release version pin to X.Y.Z, then refresh the backend venv.

The pin list lives in ``release_tag.PINS`` (the same list CI verifies before
tagging). Writing the ``docs/upgrade-guide.md`` release section stays manual.
The ccas package's version is dynamic (hatch reads ``__init__.py``), so the
editable install's metadata goes stale after a bump; ``uv sync
--reinstall-package ccas`` refreshes it unless ``--no-sync`` is given.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys

from release_tag import PINS, pin_matches


def bump(root, version):
    broken = [pin.label for pin in PINS if len(pin_matches(root, pin)) != 1]
    if broken:
        for label in broken:
            print(f"bump_version: {label}: pin missing or duplicated", file=sys.stderr)
        return None
    texts = {}
    for pin in PINS:
        text = texts.get(pin.path) or (root / pin.path).read_text(encoding="utf-8")
        match = pin.pattern.search(text)
        texts[pin.path] = text[:match.start(1)] + version + text[match.end(1):]
    changed = []
    for rel, text in texts.items():
        path = root / rel
        if path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            changed.append(rel)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="X.Y.Z (a leading v is accepted)")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--no-sync", action="store_true",
                        help="skip refreshing the backend editable install")
    args = parser.parse_args(argv)

    version = args.version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"bump_version: expected X.Y.Z, got {args.version!r}", file=sys.stderr)
        return 2
    changed = bump(args.root, version)
    if changed is None:
        return 1
    for rel in changed:
        print(rel)
    if not args.no_sync:
        subprocess.run(["uv", "sync", "-q", "--reinstall-package", "ccas"],
                       cwd=args.root / "backend", check=True)
    print(f"bump_version: pins set to {version}; add the v{version} section to "
          "docs/upgrade-guide.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
