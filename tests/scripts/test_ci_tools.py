"""Behavioral checks for the documentation lane and its aggregate gate."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.test")
        self.git("config", "user.name", "Test")
        (self.root / "README.md").write_text("initial\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True)

    def commit(self):
        self.git("add", ".")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")

    def plan(self):
        return load("ci_plan").classify(self.root, self.base, "HEAD")

    def test_only_documentation_uses_light_lane(self):
        (self.root / "README.md").write_text("updated\n")
        self.commit()
        self.assertTrue(self.plan()["docs_only"])

    def test_code_config_unknown_and_symlink_fail_closed(self):
        for filename in ["app.py", ".github/workflows/ci.yaml", "unknown.md"]:
            with self.subTest(filename=filename):
                p = self.root / filename
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("change\n")
                self.commit()
                self.assertFalse(self.plan()["docs_only"])
        self.git("reset", "--hard", self.base)
        (self.root / "README.md").unlink()
        (self.root / "README.md").symlink_to("outside")
        self.commit()
        self.assertFalse(self.plan()["docs_only"])

    def test_rename_from_code_to_docs_is_full(self):
        (self.root / "app.py").write_text("code\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("mv", "app.py", "GLOSSARY.md")
        self.commit()
        self.assertFalse(self.plan()["docs_only"])

    def test_rename_between_allowed_documents_stays_light(self):
        (self.root / "docs").mkdir()
        self.git("mv", "README.md", "docs/README.md")
        self.commit()
        self.assertTrue(self.plan()["docs_only"])

    def test_missing_base_and_empty_diff_are_full(self):
        self.assertFalse(self.plan()["docs_only"])
        self.base = "0" * 40
        self.assertFalse(self.plan()["docs_only"])

    def test_document_rename_detects_stale_links_in_unchanged_docs(self):
        (self.root / "GLOSSARY.md").write_text("terms\n")
        (self.root / "README.md").write_text("[terms](GLOSSARY.md)\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("mv", "GLOSSARY.md", "docs.md")
        self.commit()
        errors = load("check_docs").check(self.root)
        self.assertTrue(any("GLOSSARY.md" in error for error in errors))

    def test_links_resolve_relative_spaces_fragments_and_ignore_examples(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "with space.md").write_text("# Terms\n")
        (self.root / "README.md").write_text(
            "[terms](<docs/with space.md#terms>)\n"
            "[external](https://example.test/missing)\n"
            "```md\n[example](not-real.md)\n```\n"
        )
        self.commit()
        self.assertEqual(load("check_docs").check(self.root), [])

    def test_document_symlink_is_not_read(self):
        (self.root / "README.md").unlink()
        (self.root / "README.md").symlink_to("/etc/passwd")
        self.commit()
        self.assertTrue(any("symlink" in error for error in load("check_docs").check(self.root)))

    def test_parenthesized_links_and_inline_examples(self):
        (self.root / "terms(v2).md").write_text("# Terms\n")
        (self.root / "README.md").write_text(
            "[terms](terms(v2).md)\n"
            r"[escaped](terms\(v2\).md)" + "\n"
            "Use `[example](missing.md)` as syntax.\n"
            "Use ``[example](also-missing.md)`` with double ticks.\n"
        )
        self.commit()
        self.assertEqual(load("check_docs").check(self.root), [])


class GateTests(unittest.TestCase):
    def test_gate_requires_all_expected_results(self):
        module = load("ci_plan")
        needs = {name: {"result": "success"} for name in module.CODE_JOBS}
        needs.update({"plan": {"result": "success", "outputs": {"docs_only": "false"}},
                      "docs-check": {"result": "success"},
                      "scripts-checks": {"result": "success"}})
        self.assertTrue(module.gate(needs))
        needs["backend-test"]["result"] = "skipped"
        self.assertFalse(module.gate(needs))
        needs["plan"]["outputs"]["docs_only"] = "true"
        for name in module.CODE_JOBS:
            needs[name]["result"] = "skipped"
        self.assertTrue(module.gate(needs))
        needs["docs-check"]["result"] = "failure"
        self.assertFalse(module.gate(needs))
        self.assertFalse(module.gate({}))


if __name__ == "__main__":
    unittest.main()
