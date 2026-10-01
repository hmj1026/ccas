# Gemini CLI Project Context

> Shared project context is in [CLAUDE.md](./CLAUDE.md). This file contains only Gemini-specific information.

## Platform Differences

- Slash commands use **TOML format** when provisioned locally: `.gemini/commands/opsx/*.toml`
- Skills are provisioned by the runtime installer; `.gemini/skills/` is local-only and is not committed.

## DHPK Runtime Skills

| Skill | Purpose |
|-------|---------|
| `code-trace` | Structured code tracing and root-cause investigation (replaces retired `bug-investigation`) |
| `git-smart-commit` | Intelligent commit message generation and splitting |
| `dhpk-module-design` | DHPK's canonical architecture and module-boundary skill |

## Gemini-Exclusive Commands

When provisioned locally, `.gemini/commands/` contains shared `opsx/` namespace commands plus:
- `gemini-commit.toml` -- corresponds to `git-smart-commit` skill

## Synchronization

Do not vendor or manually sync installed skills or generated command directories into this repository.
