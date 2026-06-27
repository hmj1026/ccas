# CCAS — Credit Card Automation System

Gmail PDF → decrypt → parse → classify → REST API / Telegram notification.

## On-Demand Skills

| Scenario | Skill |
|---|---|
| Daily commands (test/lint/pipeline/server/alembic/seed) | `ccas-dev-commands` |
| Tech stack overview, onboarding, tech evaluation | `ccas-tech-stack` |
| `.env`, env vars, Vite proxy, Docker env_file | `ccas-env-config` |
| OpenSpec spec-driven workflow | `/opsx:*` series |
| Bug root-cause investigation | `bug-investigation` |
| Architecture decisions, module boundaries | `software-architecture` |
| Full product acceptance, QA, smoke test | `ccas-qa-acceptance` |
| Free-text task routing (feature/bug/maintenance) | `/dhpk:do` |
| Feature development workflow | `/dhpk:feature-dev` |
| Harness audit & optimization | `/dhpk:harness-audit` |

## Rules (`.claude/rules/`)

- `execution-policy.md` — task classification, agent roster (dhpk-preferred), process gates, anti-loop
- `skill-policy.md` — skill selection priority when multiple match
- `tool-decision.md` — GitNexus / cx / file tool cost hierarchy, impact exemptions, memory thresholds
- `python.md` / `python-api.md` / `python-db.md` / `python-testing.md` — backend conventions
- `frontend-typescript.md` — frontend conventions
- `parser-development.md` — bank parser registry pattern, PDF parsing conventions
- `docker-deploy.md` — multi-stage builds, SSOT sync pairs, deployment iron laws

## Key Conventions

- Responses in **Traditional Chinese**
- Branch/change names use **kebab-case** (e.g., `add-user-auth`)
- **CLAUDE.md is SSOT** for project description — do not duplicate
- Use `AskUserQuestion` when skill input is ambiguous; track task progress with checkboxes

## Skills & External Deps

Skill sources: (1) `npx skills` CLI → `.agents/skills/`; (2) Claude plugin manifest → `.claude/skills/`; (3) self-written in `.agents/skills/`.

CCAS custom skills: `ccas-dev-commands`, `ccas-env-config`, `ccas-qa-acceptance`, `ccas-tech-stack`.

Do not vendor or manually sync: `openspec`, `codex`, `pyright-lsp` — managed by their own manifests/lock files.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ccas** (14771 symbols, 21210 relationships, 137 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/ccas/context` | Codebase overview, check index freshness |
| `gitnexus://repo/ccas/clusters` | All functional areas |
| `gitnexus://repo/ccas/processes` | All execution flows |
| `gitnexus://repo/ccas/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
