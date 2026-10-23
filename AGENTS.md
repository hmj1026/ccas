# Codex Agent Guidelines

> Shared project context is in [CLAUDE.md](./CLAUDE.md). For pipeline, API/auth, storage, integration, deployment, or frontend tasks, start with [current implementation](./docs/CODEMAPS/current-implementation.md) and follow its detail map for the affected area. This file contains only Codex-specific information.

## Platform Differences

- Codex has **skills only** (no slash commands directory)
- Skills are supplied by the runtime skill catalog and local installer; `.codex/skills/` is not a repository source directory.
- Agent client directories and installed skill files (`.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `.agents/`, `.agent/`) are local-only and must not be committed.
- Tool availability comes from the current runtime; use available clarification tools only when a material decision cannot be inferred.

## Skill Sources (Codex)

Codex skills are supplied by the runtime skill catalog. This repository does not
vendor a project-local skill source or a checked-in provider projection. Do not
infer skill availability from a path that is absent from the checkout.

Do not vendor or manually sync ECC reference skills (`everything-claude-code`), `openspec`, `codex`, or `pyright-lsp`.

## Additional Skills

| Skill | Purpose |
|-------|---------|
| `code-trace` | Structured code tracing and root-cause investigation (replaces retired `bug-investigation`) |
| `dhpk-module-design` | DHPK's canonical architecture and module-boundary skill; it is not a project-local Codex symlink |

Claude-only ECC/reference skills are not additional entries under the repository.

## Semantic Code Navigation (cx)

For code exploration use `cx`. Reference: `~/.claude/CX.md` (global, all projects).

## Code navigation

When exploring code, assessing symbol changes, or preparing a commit, follow
[code navigation and phase isolation](docs/agents/code-navigation.md) for the
GitNexus impact/review gates, evidence reporting, and worktree guidance.
