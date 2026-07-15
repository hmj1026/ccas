# Skill Selection Policy

## Priority Order (when multiple skills match)

1. **OpenSpec** (new/continue/apply/verify/sync/archive) — triggers: "create change", "new feature spec", "archive", "sync specs"
2. **bug-investigation** — triggers: "investigate", "trace", "why", "diagnose", "find root cause", "root cause"
3. **dhpk:tdd-guide** agent (feature or bugfix needing test changes)
4. **software-architecture** — triggers: "architecture", "cross-module design", "refactoring direction", "system design"
5. **Other npx skills** (python-patterns, backend-patterns, api-design, etc. — from `.agents/skills`) — minimum necessary set

## Principles

- **Use because necessary, not because available**: having a related skill does not mean it must be launched
- **Implement small changes directly**: do not apply full workflow skills to minor changes (avoid over-ritualization)
- **execution-policy takes precedence**: once task classification routes through execution-policy, follow its agent flow and do not re-trigger this priority order
- **Local version wins on name conflict**: if `.agents/skills/` has a same-named version, it takes precedence over a same-named plugin skill
- **software-architecture is a general guide**: that skill includes JS/npm recommendations (arrow functions, Redux, etc.) irrelevant to the CCAS Python backend; when conflicts arise, defer to project rules (`python.md`, `python-api.md`)

> Mandatory post-steps and the Agent Roster are in `execution-policy.md`.
