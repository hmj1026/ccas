"""Behavioral checks for the release version pins, bump_version.py and release_tag.py."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


release_tag = load("release_tag")


class TagForTitleTests(unittest.TestCase):
    def test_release_title_yields_tag(self):
        self.assertEqual(release_tag.tag_for_title("Release v0.14.0"), "v0.14.0")

    def test_other_titles_yield_none(self):
        for title in ("fix: Release v0.14.0", "Release v0.14", "Release v0.14.0-rc.1",
                      "Release 0.14.0", "Release v0.14.0 hotfix", ""):
            with self.subTest(title=title):
                self.assertIsNone(release_tag.tag_for_title(title))


class RepositoryPinTests(unittest.TestCase):
    def test_every_pin_matches_exactly_once_and_all_agree(self):
        versions = release_tag.read_pins(ROOT)
        self.assertEqual(len(versions), len(release_tag.PINS))
        self.assertNotIn(None, versions.values(), versions)
        self.assertEqual(len(set(versions.values())), 1, versions)


class PinFixture(unittest.TestCase):
    """Copies the live pinned files into a scratch root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in {pin.path for pin in release_tag.PINS}:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, self.root / rel)
        self.current = next(iter(release_tag.read_pins(ROOT).values()))

    def snapshot(self):
        return {rel: (self.root / rel).read_text(encoding="utf-8")
                for rel in {pin.path for pin in release_tag.PINS}}


class BumpTests(PinFixture):
    def run_bump(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "bump_version.py"), *args,
             "--root", str(self.root), "--no-sync"],
            capture_output=True, text=True,
        )

    def test_bump_rewrites_every_pin(self):
        result = self.run_bump("9.8.7")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(release_tag.read_pins(self.root).values()), {"9.8.7"})

    def test_bump_touches_only_pin_spans(self):
        before = self.snapshot()
        self.assertEqual(self.run_bump("9.8.7").returncode, 0)
        self.assertEqual(self.run_bump(self.current).returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_bump_accepts_leading_v(self):
        self.assertEqual(self.run_bump("v9.8.7").returncode, 0)
        self.assertEqual(set(release_tag.read_pins(self.root).values()), {"9.8.7"})

    def test_bump_rejects_non_semver(self):
        before = self.snapshot()
        result = self.run_bump("9.8")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.snapshot(), before)

    def test_bump_refuses_when_a_pin_is_missing(self):
        path = self.root / "docs/mcp-installation.md"
        path.write_text("no pin here\n", encoding="utf-8")
        before = self.snapshot()
        result = self.run_bump("9.8.7")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/mcp-installation.md", result.stderr)
        self.assertEqual(self.snapshot(), before)


class ResolveTests(PinFixture):
    def setUp(self):
        super().setUp()
        self.output = self.root / "github_output"
        self.tag = f"v{self.current}"

    def run_cli(self, title):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "release_tag.py"), "--title", title,
             "--root", str(self.root), "--github-output", str(self.output)],
            capture_output=True, text=True,
        )

    def test_matching_pins_emit_tag(self):
        result = self.run_cli(f"Release {self.tag}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), f"tag={self.tag}\n")

    def test_non_release_title_emits_empty_tag(self):
        result = self.run_cli("feat: something")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), "tag=\n")

    def test_malformed_release_title_fails(self):
        result = self.run_cli("Release v0.14")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Release vX.Y.Z", result.stderr)
        self.assertFalse(self.output.exists())

    def test_any_stale_pin_fails_and_names_file(self):
        for pin in release_tag.PINS:
            with self.subTest(pin=pin.label):
                saved = self.snapshot()
                path = self.root / pin.path
                text = path.read_text(encoding="utf-8")
                match = pin.pattern.search(text)
                path.write_text(text[:match.start(1)] + "0.0.1" + text[match.end(1):],
                                encoding="utf-8")
                result = self.run_cli(f"Release {self.tag}")
                self.assertEqual(result.returncode, 1)
                self.assertIn(pin.path, result.stderr)
                self.assertFalse(self.output.exists())
                for rel, content in saved.items():
                    (self.root / rel).write_text(content, encoding="utf-8")

    def test_missing_pin_file_fails(self):
        (self.root / "docs/install-quickstart.md").unlink()
        result = self.run_cli(f"Release {self.tag}")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/install-quickstart.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
