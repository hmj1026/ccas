# Gemini CLI Project Context

> Shared project context is in [CLAUDE.md](./CLAUDE.md). This file contains only Gemini-specific information.

## Platform Differences

- Slash commands use **TOML format**: `.gemini/commands/opsx/*.toml`
- Skills are defined in `.gemini/skills/<name>/SKILL.md`
- This repo's tracked `.gemini/skills/` contains only the OpenSpec workflow skills. DHPK skills are provisioned at runtime; consult the installer/receipt for the current roster.

## DHPK Runtime Skills

| Skill | Purpose |
|-------|---------|
| `code-trace` | Structured code tracing and root-cause investigation (replaces retired `bug-investigation`) |
| `git-smart-commit` | Intelligent commit message generation and splitting |
| `dhpk-module-design` | DHPK's canonical architecture and module-boundary skill |

## Gemini-Exclusive Commands

`.gemini/commands/` contains shared `opsx/` namespace commands plus:
- `gemini-commit.toml` -- corresponds to `git-smart-commit` skill

## Synchronization

When updating OpenSpec skills, sync the tracked provider directories together. DHPK-generated `.codex/skills/` projections are installer-managed and must not be committed as cross-repository symlinks.
