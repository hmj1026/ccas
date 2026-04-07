---
paths:
  - ".claude/skills/**"
  - ".codex/skills/**"
  - ".gemini/skills/**"
  - ".claude/commands/**"
  - ".gemini/commands/**"
---
# Multi-Platform Skill Parity

## Skill Definitions

The 10 OpenSpec skills + 2 general-purpose skills are defined in three formats:

| Platform | Location | Format | Count |
|----------|----------|--------|-------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | Markdown + YAML frontmatter | 12 |
| Codex | `.codex/skills/<name>/SKILL.md` | Same format, skills only | 12 |
| Gemini | `.gemini/skills/<name>/SKILL.md` | Same format | 13 (+ `git-smart-commit`) |

## Commands

| Platform | Location | Format |
|----------|----------|--------|
| Claude Code | `.claude/commands/opsx/*.md` | Markdown |
| Gemini | `.gemini/commands/opsx/*.toml` | TOML |
| Codex | (none) | No commands directory (batch mode) |

Gemini additionally has `gemini-commit.toml` for the `git-smart-commit` skill.

## Synchronization Rules

1. When modifying an OpenSpec skill, update all three platforms
2. `bug-investigation` and `software-architecture` exist in all three
3. `git-smart-commit` is Gemini-exclusive -- do not create Claude/Codex equivalents
4. The `.claude/hooks/ccas-skill-sync-check.sh` hook will warn on skill file changes
