"""Verdict logic for check_release_images.py (registry access is injected)."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "check_release_images", ROOT / "scripts" / "check_release_images.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SHA = "1738c0d0123456789abcdef0123456789abcdef0"


def index(*arches):
    return {"manifests": [{"digest": f"sha256:{a}", "platform": {"architecture": a}}
                          for a in arches]
            + [{"digest": "sha256:att", "platform": {"architecture": "unknown"}}]}


class FakeRegistry:
    def __init__(self, tags, revision=SHA):
        self.tags = tags  # tag -> (digest, index) or None
        self.revision = revision

    def index(self, image, tag):
        return self.tags.get(tag)

    def revision_of(self, image, manifest_digest):
        return self.revision


def healthy():
    entry = ("sha256:idx", index("amd64", "arm64"))
    return {"v0.13.1": entry, "sha-1738c0d": entry}


class VerdictTests(unittest.TestCase):
    def problems(self, registry):
        return mod.check_image(registry, "ccas-backend", "v0.13.1", SHA)

    def test_healthy_image_has_no_problems(self):
        self.assertEqual(self.problems(FakeRegistry(healthy())), [])

    def test_missing_release_tag(self):
        tags = healthy()
        del tags["v0.13.1"]
        self.assertIn("v0.13.1 not found", self.problems(FakeRegistry(tags))[0])

    def test_digest_differs_from_merge_commit_build(self):
        tags = healthy()
        tags["sha-1738c0d"] = ("sha256:other", index("amd64", "arm64"))
        self.assertIn("differs from sha-1738c0d", " ".join(self.problems(FakeRegistry(tags))))

    def test_missing_arm64(self):
        entry = ("sha256:idx", index("amd64"))
        found = self.problems(FakeRegistry({"v0.13.1": entry, "sha-1738c0d": entry}))
        self.assertIn("arm64", " ".join(found))

    def test_revision_label_mismatch(self):
        found = self.problems(FakeRegistry(healthy(), revision="deadbeef"))
        self.assertIn("revision", " ".join(found))


if __name__ == "__main__":
    unittest.main()
