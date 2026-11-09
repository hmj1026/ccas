"""Monitor tests use gh responses, never a network connection or real merge."""

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location("watch_pr", ROOT / "scripts/watch_pr.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def snapshot(sha="a" * 40, checks=None):
    return {"state": "OPEN", "headRefOid": sha, "mergeStateStatus": "CLEAN",
            "statusCheckRollup": checks if checks is not None else [
                {"name": "CI Gate", "status": "COMPLETED", "conclusion": "SUCCESS"}]}


class WatchTests(unittest.TestCase):
    def exercise(self, states, **options):
        calls, events = [], []
        values = iter(states)

        def run(args):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(next(values))
            return "{}"

        result = module().watch("1", "owner/repo", ["CI Gate"],
                                run=run, emit=events.append, sleep=lambda _: None,
                                timeout=10, interval=1, **options)
        return result, calls, events

    def test_merge_uses_full_sha_and_second_snapshot(self):
        result, calls, _ = self.exercise([snapshot(), snapshot(),
                                         {"state": "MERGED", "headRefOid": "a" * 40}], merge=True)
        self.assertEqual(result, 0)
        merge = next(c for c in calls if c[:3] == ["gh", "pr", "merge"])
        self.assertEqual(merge[merge.index("--match-head-commit") + 1], "a" * 40)
        self.assertEqual(sum(c[:3] == ["gh", "pr", "view"] for c in calls), 3)

    def test_head_change_before_merge_is_blocked(self):
        result, calls, _ = self.exercise([snapshot(), snapshot("b" * 40)], merge=True)
        self.assertNotEqual(result, 0)
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] for c in calls))

    def test_missing_gate_and_pending_checks_do_not_merge(self):
        pending = snapshot(checks=[])
        result, calls, events = self.exercise([pending, pending, snapshot(), snapshot(),
                                             {"state": "MERGED", "headRefOid": "a" * 40}], merge=True)
        self.assertEqual(result, 0)
        self.assertEqual(sum("waiting" in e for e in events), 1)
        self.assertEqual(calls[2][:3], ["gh", "pr", "view"])

    def test_failed_check_reports_failed_steps_without_retry_or_cancel(self):
        failed = snapshot(checks=[{"name": "CI Gate", "status": "COMPLETED",
                                  "conclusion": "FAILURE",
                                  "detailsUrl": "https://github.com/owner/repo/actions/runs/123/job/456"}])
        result, calls, _ = self.exercise([failed], merge=True)
        self.assertNotEqual(result, 0)
        self.assertTrue(any(c[:3] == ["gh", "run", "view"] for c in calls))
        self.assertFalse(any("merge" in c or "cancel" in c or "rerun" in c for c in calls))

    def test_read_only_default_and_skipped_gate_cannot_pass(self):
        result, calls, _ = self.exercise([snapshot()])
        self.assertEqual(result, 0)
        self.assertFalse(any("merge" in c for c in calls))
        state, _ = module().assess(snapshot(checks=[{
            "name": "CI Gate", "status": "COMPLETED", "conclusion": "SKIPPED"}]), ["CI Gate"])
        self.assertNotEqual(state, "green")

    def test_short_sha_is_rejected(self):
        result, calls, _ = self.exercise([snapshot("abc123")], merge=True)
        self.assertNotEqual(result, 0)
        self.assertFalse(any("merge" in c for c in calls))

    def test_check_regression_immediately_before_merge_is_blocked(self):
        result, calls, _ = self.exercise([snapshot(), snapshot(checks=[])], merge=True)
        self.assertNotEqual(result, 0)
        self.assertFalse(any("merge" in c for c in calls))

    def test_timeout_does_not_mutate_workflow(self):
        ticks = iter([0, 0, 11, 11])
        calls = []

        def run(args):
            calls.append(args)
            return json.dumps(snapshot(checks=[]))

        result = module().watch("1", "owner/repo", ["CI Gate"], merge=True,
                                run=run, emit=lambda _: None, sleep=lambda _: None,
                                timeout=10, clock=lambda: next(ticks))
        self.assertEqual(result, 2)
        self.assertTrue(all(c[:3] == ["gh", "pr", "view"] for c in calls))


if __name__ == "__main__":
    unittest.main()
