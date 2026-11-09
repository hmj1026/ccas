"""Behavioral checks for the release-tag resolver used by release-tag.yaml."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release_tag.py"
PINNED = ("README.md", "README.zh-TW.md", "docs/install-quickstart.md")


def load():
    spec = importlib.util.spec_from_file_location("release_tag", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TagForTitleTests(unittest.TestCase):
    def test_release_title_yields_tag(self):
        self.assertEqual(load().tag_for_title("Release v0.14.0"), "v0.14.0")

    def test_other_titles_yield_none(self):
        for title in ("fix: Release v0.14.0", "Release v0.14", "Release v0.14.0-rc.1",
                      "Release 0.14.0", "Release v0.14.0 hotfix", ""):
            with self.subTest(title=title):
                self.assertIsNone(load().tag_for_title(title))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root / "github_output"

    def pin(self, version, skip=()):
        for rel in PINNED:
            if rel in skip:
                continue
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"RELEASE={version}      # pin\n")

    def run_cli(self, title):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--title", title, "--root", str(self.root),
             "--github-output", str(self.output)],
            capture_output=True, text=True,
        )

    def test_matching_pins_emit_tag(self):
        self.pin("v0.14.0")
        result = self.run_cli("Release v0.14.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "tag=v0.14.0\n")

    def test_non_release_title_emits_empty_tag(self):
        result = self.run_cli("feat: something")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "tag=\n")

    def test_malformed_release_title_fails(self):
        self.pin("v0.14.0")
        result = self.run_cli("Release v0.14")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Release vX.Y.Z", result.stderr)
        self.assertFalse(self.output.exists())

    def test_stale_pin_fails_and_names_file(self):
        self.pin("v0.14.0")
        (self.root / "README.zh-TW.md").write_text("RELEASE=v0.13.0\n")
        result = self.run_cli("Release v0.14.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.zh-TW.md", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_pin_file_fails(self):
        self.pin("v0.14.0", skip=("docs/install-quickstart.md",))
        result = self.run_cli("Release v0.14.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/install-quickstart.md", result.stderr)

    def test_repository_pins_agree(self):
        # The live checkout must stay internally consistent across all pins.
        tags = {load().pinned_tag(ROOT / rel) for rel in PINNED}
        self.assertEqual(len(tags), 1, tags)


if __name__ == "__main__":
    unittest.main()
