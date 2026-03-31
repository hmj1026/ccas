# Gemini CLI Project Context

> Shared project context is in [CLAUDE.md](./CLAUDE.md). This file contains only Gemini-specific information.

## Platform Differences

- Slash commands use **TOML format**: `.gemini/commands/opsx/*.toml`
- Skills are defined in `.gemini/skills/<name>/SKILL.md`

## Gemini-Exclusive Skills

| Skill | Purpose |
|-------|---------|
| `bug-investigation` | Structured bug triage and root cause analysis |
| `git-smart-commit` | Intelligent commit message generation and splitting |
| `software-architecture` | Architecture decision records |

## Gemini-Exclusive Commands

`.gemini/commands/` contains shared `opsx/` namespace commands plus:
- `gemini-commit.toml` -- corresponds to `git-smart-commit` skill

## Synchronization

When updating OpenSpec skills, sync `.gemini/skills/`, `.claude/skills/`, and `.codex/skills/` together.
