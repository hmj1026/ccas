#!/usr/bin/env python3
"""Verify the published GHCR images for a release tag, anonymously.

For each image: ``vX.Y.Z`` exists, its index digest equals the
``sha-<merge commit>`` build, it carries amd64 and arm64, and the amd64
config's ``org.opencontainers.image.revision`` is the tag's commit. Uses the
public registry token endpoint, so no ``read:packages`` scope is needed.
Exits 1 and lists every problem when any check fails.
"""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

IMAGES = ("ccas-backend", "ccas-frontend", "ccas-proxy")
ARCHES = ("amd64", "arm64")
INDEX_TYPES = ("application/vnd.oci.image.index.v1+json, "
               "application/vnd.docker.distribution.manifest.list.v2+json")
MANIFEST_TYPES = ("application/vnd.oci.image.manifest.v1+json, "
                  "application/vnd.docker.distribution.manifest.v2+json")


class Registry:
    def __init__(self, owner, host="ghcr.io"):
        self.owner, self.host, self.tokens = owner, host, {}

    def _get(self, image, path, accept):
        repo = f"{self.owner}/{image}"
        if repo not in self.tokens:
            url = f"https://{self.host}/token?scope=repository:{repo}:pull"
            with urllib.request.urlopen(url, timeout=30) as resp:
                self.tokens[repo] = json.load(resp)["token"]
        req = urllib.request.Request(
            f"https://{self.host}/v2/{repo}/{path}",
            headers={"Authorization": f"Bearer {self.tokens[repo]}", "Accept": accept})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.headers.get("Docker-Content-Digest"), json.load(resp)

    def index(self, image, tag):
        try:
            return self._get(image, f"manifests/{tag}", INDEX_TYPES)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return None
            raise

    def revision_of(self, image, manifest_digest):
        _, manifest = self._get(image, f"manifests/{manifest_digest}", MANIFEST_TYPES)
        _, config = self._get(image, f"blobs/{manifest['config']['digest']}", "*/*")
        labels = config.get("config", {}).get("Labels") or {}
        return labels.get("org.opencontainers.image.revision")


def check_image(registry, image, tag, commit):
    problems = []
    release = registry.index(image, tag)
    if release is None:
        return [f"{image}: {tag} not found"]
    digest, index = release
    short = f"sha-{commit[:7]}"
    build = registry.index(image, short)
    if build is None or build[0] != digest:
        problems.append(f"{image}: {tag} digest {digest} differs from {short} "
                        f"({build[0] if build else 'missing'})")
    platforms = {m["platform"]["architecture"]: m["digest"]
                 for m in index.get("manifests", []) if "platform" in m}
    missing = [arch for arch in ARCHES if arch not in platforms]
    if missing:
        problems.append(f"{image}: {tag} lacks {', '.join(missing)}")
    if "amd64" in platforms:
        revision = registry.revision_of(image, platforms["amd64"])
        if revision != commit:
            problems.append(f"{image}: revision label {revision} != {commit}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="release tag, e.g. v0.13.1")
    parser.add_argument("--owner", default="hmj1026")
    args = parser.parse_args(argv)

    commit = subprocess.run(["git", "rev-parse", f"{args.tag}^{{commit}}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    registry = Registry(args.owner)
    problems = []
    for image in IMAGES:
        found = check_image(registry, image, args.tag, commit)
        problems += found
        print(f"{image}: {'FAIL' if found else 'OK'}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
