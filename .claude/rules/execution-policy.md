---
paths:
  - "**/*.py"
  - "**/*.md"
  - "**/*.yaml"
  - "**/*.toml"
---
# Claude Code Execution Policy

## Task Modes

Default: execute directly toward user's goal without over-planning. All flows end with mandatory post-steps (see below).

| Scale | Flow |
|---------|------|
| **Small change (non-bug-fix)** | inspect → patch |
| **Small change (known-root bug fix)** | inspect → tdd (write RED test) → patch → tdd (verify GREEN) |
| **Medium change** | inspect → brief plan → tdd → patch |
| **Bug fix (unknown root cause)** | bug-investigation → tdd → patch |
| **New feature** | [OpenSpec?]¹ → tdd → patch |
| **Architecture change** | software-architecture → [OpenSpec?]¹ → tdd → patch |

¹ `[OpenSpec?]` = optional step, ask user (default n):
- **y** → `/opsx:new`, create `openspec/changes/<name>/` artifacts
- **n** → brief plan (list steps in reply), no artifacts

## Mandatory Post-steps (No Exceptions)

| Trigger | Must Launch Agent | Timing |
|---------|--------------|---------|
| Any Edit/Write | `python-reviewer` (ECC) | Last step |
| Bug fix or new feature | `tdd-guide` (ECC) | Before python-reviewer |
| SQL / Alembic operation | `database-reviewer` (ECC) | Before python-reviewer |
| Auth / input validation / secrets | `security-reviewer` (ECC) | Before python-reviewer |

**Order** (when multiple trigger): tdd-guide → database-reviewer → security-reviewer → python-reviewer

**Exemptions:**
- Pure research/planning (no Edit/Write) → skip python-reviewer
- **Small change (inspect → patch, non-bug-fix, non-feature) → PostToolUse hooks static analysis is sufficient; python-reviewer not required**

## Output Contract

Reply format for each task:
```
Conclusion (what was done)
→ Verification (how to confirm correctness)
→ Risks / pending items (if any)
```

## Anti-Loop Protocol

If the same issue fails **3 times**, **STOP immediately** and report:
1. **Attempt log**: what was tried, error messages
2. **Alternatives**: at least 2 viable paths with trade-offs
3. **Recommendation**: suggested next step with rationale

## OpenSpec Workflow

Artifacts directory: `openspec/changes/<name>/` (proposal → specs → design → tasks → archive)

**IMPORTANT: `tasks.md` must be created before implementation begins; writing code before documentation is prohibited.**

## ECC Agent Roster

> All agents listed here come from the external `everything-claude-code` plugin — not vendored or maintained in this project. This policy only governs "when to trigger", not the agents themselves.

| Phase | Agent | Slash Command | When |
|-------|-------|--------------|------|
| Planning | `planner` | `/plan` | Complex features, multi-file changes |
| Architecture | `architect` | -- | System design decisions |
| TDD | `tdd-guide` | `/tdd` | Before writing implementation code |
| Code Review | `python-reviewer` | `/python-review` | After Python code changes |
| Code Review | `code-reviewer` | `/code-review` | After any code changes |
| Security | `security-reviewer` | -- | Auth, user input, API endpoints, secrets |
| Database | `database-reviewer` | -- | SQLAlchemy queries, schema design, migrations |
| Build Fix | `build-error-resolver` | `/build-fix` | Build or type errors |
| Docs | `doc-updater` | `/update-docs` | Documentation updates |

Relevant ECC skills: `python-patterns`, `python-testing`, `backend-patterns`, `api-design`, `database-migrations`, `tdd-workflow`, `security-review`, `docker-patterns`

## Self-Check Checklist (before each task reply)

| # | Trigger | Check | Rule |
|---|---|---|---|
| 0 | **Is this a small change?** (inspect → patch; non-bug-fix; non-feature; **and no SSOT file touched**) | Handle hook warnings; skip 1–7 | This file "Task Modes" |
| 1 | After Edit/Write to Python feature | Was `python-reviewer` run? | This file "Mandatory Post-steps" |
| 2 | Bug fix or new feature | Was `tdd-guide` run? | This file "Mandatory Post-steps" |
| 3 | SQL / Alembic change | Was `database-reviewer` run? Was `alembic upgrade head` applied? | `python-db.md` |
| 4 | Any Python file changed | Did both `ruff check` + **`ruff format --check`** pass? (avoid CI format failure) | `python.md` |
| 5 | Frontend test config / `frontend/e2e/*.spec.ts` changed | Distinguish runners: `pnpm test` = Vitest (`src/**`); Playwright uses `pnpm e2e` | `frontend-typescript.md` |
| 6 | **Any SSOT file changed** (`scripts/docker-entrypoint.sh`, `scripts/check-env.sh`, `.env.example`, `config/*.example.yaml`) | Was `./scripts/sync-docker-image-assets.sh` run? Are mirrors staged? | `docker-deploy.md` "SSOT Sync" |
| 7 | Dockerfile / docker-compose changed | Did `docker compose config` validate? Production stage changes need local build verification | `docker-deploy.md` |

**Item 0 small-change exemption condition**: "Touching any SSOT file disqualifies the small-change exemption" (prevents SSOT drift from slipping through as small change).

## PostToolUse Hooks (hook–rule mapping)

The following hooks run automatically after Edit/Write via `.claude/settings.json` — they are the **warning layer** and do not replace rules. A rule covered by a hook must still be written in the rules file in human-readable form.

| Hook | Coverage | Corresponding Rule |
|---|---|---|
| `ccas-python-lint.sh` | Python Edit/Write: real-time ruff + bandit warning | `python.md` |
| `ccas-sqlalchemy-model-check.sh` | `**/models*.py`: real-time ORM convention validation | `python-db.md` |
| `ccas-tdd-red-check.sh` | New test files in `tests/`: run file to confirm RED | `python-testing.md` |
| `ccas-frontend-lint.sh` | `frontend/**/*.{ts,tsx}`: real-time eslint | `frontend-typescript.md` |
| `ccas-alembic-migration-check.sh` | Migration files: real-time safety check (drop column warning etc.) | `python-db.md` |
| `ccas-docker-check.sh` | Dockerfile / compose: real-time convention validation | `docker-deploy.md` |
| `ccas-pre-push-stop.sh` (Stop event) | Session end: run full pre-push quality gate | `docker-deploy.md` "Repo-level Process Gates" |
| `ccas-session-retrospective.sh` (Stop) | Write session log | — |
