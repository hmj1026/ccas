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

## Rules (`.claude/rules/`)

- `execution-policy.md` — task classification, ECC agent roster, process gates, anti-loop
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

Do not vendor or manually sync: `everything-claude-code`, `openspec`, `codex`, `pyright-lsp` — managed by their own manifests/lock files.

<!-- gitnexus:start -->
## GitNexus (ccas: 11,825 symbols, 16,463 relationships)

Tool selection order and impact rules: `.claude/rules/tool-decision.md`.
Skills: `.claude/skills/gitnexus/` (exploring / debugging / refactoring / impact-analysis / cli / guide).

> If index stale: run `npx gitnexus analyze` in terminal first.
<!-- gitnexus:end -->
