# Codex Agent Guidelines

> Shared project context is in [CLAUDE.md](./CLAUDE.md). This file contains only Codex-specific information.

## Platform Differences

- Codex has **skills only** (no slash commands directory)
- Skills are defined in `.codex/skills/<name>/SKILL.md`
- This repo's `.codex/skills/` contains 12 skills: the same 10 OpenSpec workflow skills as Claude, plus `bug-investigation` and `software-architecture`
- No interactive tools (no AskUserQuestion equivalent) — batch mode only: receives full prompt, returns full response

## Skill Sources (Codex)

Skill sources match CLAUDE.md: (1) `npx skills` CLI → `.agents/skills/`; (2) self-written in `.agents/skills/`. Plugin-provided skills (Claude-only) are not in `.codex/skills/`.

Do not vendor or manually sync ECC reference skills (`everything-claude-code`), `openspec`, `codex`, or `pyright-lsp`.

When updating OpenSpec skills, sync `.codex/skills/` alongside `.claude/skills/`.

## Additional Skills

| Skill | Purpose |
|-------|---------|
| `bug-investigation` | Structured bug triage and root cause analysis |
| `software-architecture` | Architecture decision records |

Claude-only ECC/reference skills are not additional entries under `.codex/skills/`.

## Semantic Code Navigation (cx)

For code exploration use `cx`. Reference: `~/.claude/CX.md` (global, all projects).

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ccas** (14165 symbols, 20102 relationships, 132 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
