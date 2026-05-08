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
