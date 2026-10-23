#!/usr/bin/env python3
"""Check local Markdown link destinations across tracked documentation.

Checks file existence, including image/reference links; remote URLs and heading
anchors are outside this offline check. Fenced examples are not live links.
"""

import argparse
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


def link_target(value):
    if value.startswith("<"):
        end = value.find(">")
        return value[1:end] if end >= 0 else ""
    result, depth, escaped = [], 0, False
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "(":
            depth += 1
            result.append(char)
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
            result.append(char)
        elif char.isspace():
            break
        else:
            result.append(char)
    return "".join(result)


def destinations(text):
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        line = re.sub(r"(`+).*?\1", "", line)
        for match in re.finditer(r"(?<!\\)\[[^\]]*\]\(\s*", line):
            yield number, link_target(line[match.end():])
        definition = re.match(r"^\s*\[[^\]]+\]:\s*", line)
        if definition:
            yield number, link_target(line[definition.end():])


def check(root):
    root = root.resolve()
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    errors = []
    for raw in files:
        if not raw:
            continue
        relative = raw.decode("utf-8")
        source = root / relative
        if source.suffix != ".md":
            continue
        if source.is_symlink():
            errors.append(f"{relative}: symlink documentation is not inspected")
            continue
        if not source.is_file():
            continue
        for line, target in destinations(source.read_text()):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            # Leading slash in repository Markdown resolves from the repo root.
            path = unquote(url.path)
            destination = (root / path.lstrip("/")) if path.startswith("/") else (source.parent / path)
            if not destination.exists():
                errors.append(f"{relative}:{line}: missing link destination: {target}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    errors = check(args.root)
    for error in errors:
        print(error)
    print(f"Documentation links: {'FAIL' if errors else 'PASS'}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
