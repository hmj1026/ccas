# Codex Agent Guidelines

> Shared project context is in [CLAUDE.md](./CLAUDE.md). This file contains only Codex-specific information.

## Platform Differences

- Codex has **skills only** (no slash commands directory)
- Skills are defined in `.codex/skills/<name>/SKILL.md`
- Same 10 OpenSpec skills as Claude, plus `bug-investigation` and `software-architecture`

## Codex Limitations

- No interactive tools (no AskUserQuestion equivalent)
- Batch mode: receives full prompt, returns full response
- When updating OpenSpec skills, sync `.codex/skills/` alongside `.claude/skills/` and `.gemini/skills/`

## Additional Skills

| Skill | Purpose |
|-------|---------|
| `bug-investigation` | Structured bug triage and root cause analysis |
| `software-architecture` | Architecture decision records |
