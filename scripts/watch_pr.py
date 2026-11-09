#!/usr/bin/env python3
"""Watch a fixed PR head; merge only with explicit --merge and passing checks.

This tool never cancels or retries jobs. Timeout is an observation boundary,
not evidence of a hung runner. Commands use the current gh authentication.
"""

import argparse
import json
import re
import subprocess
import time

FIELDS = "state,headRefOid,mergeStateStatus,statusCheckRollup,url"


def gh(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=60)


def check_state(check):
    if "conclusion" in check:
        return check.get("conclusion") if check.get("status") == "COMPLETED" else "PENDING"
    return check.get("state", "PENDING")


def assess(snapshot, required):
    checks = snapshot.get("statusCheckRollup") or []
    failed = [c.get("name", c.get("context", "unknown")) for c in checks
              if check_state(c) in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STALE"}]
    if failed:
        return "failed", ", ".join(failed)
    missing = [name for name in required if not any(
        c.get("name", c.get("context")) == name and check_state(c) == "SUCCESS" for c in checks)]
    pending = [c.get("name", c.get("context", "unknown")) for c in checks
               if check_state(c) not in {"SUCCESS", "SKIPPED"}]
    if missing or pending:
        return "waiting", ", ".join(sorted(set(missing + pending)))
    if snapshot.get("mergeStateStatus") != "CLEAN":
        return "waiting", "merge state: " + str(snapshot.get("mergeStateStatus"))
    return "green", "all checks completed; required checks passed"


def failure_details(snapshot, repo, run, emit):
    runs = set()
    for check in snapshot.get("statusCheckRollup") or []:
        if check_state(check) in {"SUCCESS", "SKIPPED", "PENDING"}:
            continue
        match = re.search(r"/actions/runs/(\d+)", check.get("detailsUrl", ""))
        if match:
            runs.add(match[1])
    for run_id in sorted(runs):
        try:
            jobs = json.loads(run(["gh", "run", "view", run_id, "--repo", repo, "--json", "jobs"]))
            for job in jobs.get("jobs", []):
                if job.get("conclusion") not in {"success", "skipped", None, ""}:
                    steps = [s["name"] for s in job.get("steps", [])
                             if s.get("conclusion") not in {"success", "skipped", None, ""}]
                    emit(f"failed job: {job['name']}; steps: {', '.join(steps)}")
        except (subprocess.SubprocessError, ValueError) as error:
            emit(f"failed-step details unavailable: {type(error).__name__}")


def watch(pr, repo, required, *, merge=False, interval=30, timeout=1800,
          run=gh, emit=print, sleep=time.sleep, clock=time.monotonic):
    start, expected, previous = clock(), None, None
    view = ["gh", "pr", "view", pr, "--repo", repo, "--json", FIELDS]
    while clock() - start < timeout:
        snapshot = json.loads(run(view))
        head = snapshot.get("headRefOid", "")
        if not re.fullmatch(r"[0-9a-f]{40}", head):
            emit("blocked: missing full head SHA")
            return 1
        if expected is None:
            expected = head
        if head != expected:
            emit("blocked: PR head changed; start a new observation")
            return 1
        if snapshot.get("state") == "MERGED":
            emit(f"merged: {repo}#{pr} head={head}")
            return 0
        if snapshot.get("state") != "OPEN":
            emit("blocked: PR is not open")
            return 1
        state, detail = assess(snapshot, required)
        event = f"{state}: {detail} (head={head})"
        if event != previous:
            emit(event)
            previous = event
        if state == "failed":
            failure_details(snapshot, repo, run, emit)
            return 1
        if state == "green":
            if not merge:
                return 0
            # Re-read immediately before mutation; GitHub atomically matches the
            # expected head as well. Changed/non-green evidence never merges.
            final = json.loads(run(view))
            if final.get("headRefOid") != expected or final.get("state") != "OPEN" or assess(final, required)[0] != "green":
                emit("blocked: PR changed before merge")
                return 1
            run(["gh", "pr", "merge", pr, "--repo", repo, "--merge",
                 "--match-head-commit", expected])
            confirmed = json.loads(run(view))
            if confirmed.get("state") != "MERGED" or confirmed.get("headRefOid") != expected:
                emit("blocked: merge completion not confirmed")
                return 1
            emit(f"merged: {repo}#{pr} head={expected}")
            return 0
        sleep(min(interval, max(0, timeout - (clock() - start))))
    emit("pending: observation timed out; no cancellation or retry performed")
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr")
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--required-check", action="append", default=None)
    parser.add_argument("--merge", action="store_true", help="explicitly authorize merge after checks")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.interval < 1 or args.timeout < 1:
        parser.error("interval and timeout must be positive")
    try:
        return watch(args.pr, args.repo, args.required_check or ["CI Gate"],
                     merge=args.merge, interval=args.interval, timeout=args.timeout,
                     emit=lambda text: print(text, flush=True))
    except (subprocess.SubprocessError, ValueError, OSError) as error:
        print(f"blocked: gh observation failed ({type(error).__name__}); no success inferred")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
