# CCAS — Credit Card Automation System

Gmail PDF → decrypt → parse → classify → REST API / Telegram notification.

## On-Demand Skills

| Scenario | Skill |
|---|---|
| OpenSpec spec-driven workflow | `/opsx:*` series |
| Bug root-cause investigation | `dhpk:bug-investigation` |
| Architecture decisions, module boundaries | `dhpk:software-architecture` |
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

Skills come from installed Claude plugin manifests (dhpk, openspec/`opsx`, codex, …), surfaced at runtime — they are **not** vendored in this repo. The only real directory under `.claude/skills/` is `gitnexus/` (GitNexus CLI skill docs); it is not a plugin symlink.

Do not vendor or manually sync: `openspec`, `codex`, `pyright-lsp` — managed by their own manifests/lock files.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ccas** (symbol, relationship, and execution-flow graph). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely. Exact counts live in `.gitnexus/meta.json` — query the graph rather than trusting numbers written here.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Recommended (advisory — no hook enforces these)

- **Before editing a symbol**, consider running `gitnexus_impact({target: "symbolName", direction: "upstream"})` and reporting the blast radius (direct callers, affected processes, risk level) to the user.
- **Before committing**, consider running `gitnexus_detect_changes()` to verify your changes only affect expected symbols and execution flows.
- Warn the user if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, `gitnexus_query({query: "concept"})` finds execution flows faster than grepping — it returns process-grouped results ranked by relevance.
- For full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Prefer / Avoid

- Prefer running `gitnexus_impact` before editing a function, class, or method, rather than editing blind.
- Don't ignore HIGH or CRITICAL risk warnings from impact analysis.
- Avoid renaming symbols with find-and-replace — use `gitnexus_rename`, which understands the call graph.
- Prefer running `gitnexus_detect_changes()` before committing to check affected scope.

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
