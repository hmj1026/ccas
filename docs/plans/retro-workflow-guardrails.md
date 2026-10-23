# Workflow retrospective follow-up

## Scope

The three architecture changes merged in PR #83 exposed gaps in tooling and
agent coordination. This follow-up keeps application behavior unchanged.

- The dhpk source repository owns precommit runner verdicts and repository
  command configuration, plus agent handoff and compact evidence guidance.
- ccas owns its staged-file hook, regression coverage, runner configuration,
  and shared navigation guidance. Installed client directories stay local.
- Full backend type checking remains a gate. Separate phases in worktrees or
  complete the current phase before adding the next phase's unfinished tests.

## Hook verification

`bash tests/scripts/test_pre_commit.sh` first failed because the hook rewrote
an unrelated dirty Python file. After the fix it passes, covering staged-only
formatting, whole-backend type checking, nonzero typecheck failures, and
preservation of partially staged files. CI runs this regression suite.

## Frontend timeout investigation — 2026-10-23

The prior full pre-push run timed out once in the operations trigger test
(default 5000 ms). An isolated rerun, a complete rerun, and hosted CI passed.
This observation does not establish a root cause.

The follow-up compares six sequential complete Vitest runs, three using the
default worker setting and three using `--maxWorkers=2`. Environment: macOS
27.0.1 arm64, Node 26.12.0, pnpm 10.33.4. Other local work was active, so these
are diagnostic samples rather than controlled benchmark results. They do not
reproduce hosted CI's Node 22 environment or the coverage instrumentation of
the original pre-push run.

Reproduce from `frontend/`, using distinct output paths per run:

```bash
pnpm exec vitest run --reporter=json --outputFile=/tmp/ccas-default.json
pnpm exec vitest run --maxWorkers=2 --reporter=json --outputFile=/tmp/ccas-workers2.json
```

Suite elapsed time is the maximum test-result end time minus the report start
time. Trigger duration is the operations test `submits trigger payload and
invalidates the active section`. Results are recorded below.

| Workers | Run | Passed / total | Suite (s) | Trigger (ms) |
|---|---:|---:|---:|---:|
| default | 1 | 299 / 299 | 14.09 | 1948.0 |
| default | 2 | 299 / 299 | 13.89 | 1746.3 |
| default | 3 | 299 / 299 | 13.54 | 1893.3 |
| workers2 | 1 | 299 / 299 | 26.36 | 834.6 |
| workers2 | 2 | 299 / 299 | 28.36 | 809.8 |
| workers2 | 3 | 299 / 299 | 25.48 | 913.7 |

All six runs passed. Limiting workers reduced the trigger duration but roughly
doubled total suite time. No timeout, retry, or worker setting is changed:
these samples do not establish a recurring failure or prove its cause. If the
timeout recurs, retain the JSON report, exact command, Node version, coverage
mode, and host concurrency before comparing the same workload.

## Final local verification

The updated dhpk source runner completed full mode against ccas with exit 0
and `PASS`: backend lint/format/type checks, frontend lint/build, backend unit
coverage, frontend coverage, and the hook regression. The runner's own fixture
suite passed 18 cases, including mixed-directory execution and nonzero
unsupported/failure exits. The first development run loaded an intermediate
runner revision and failed on frontend cwd; only the completed rerun is used
as acceptance evidence.
