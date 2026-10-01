# Codex Agent Guidelines

> Shared project context is in [CLAUDE.md](./CLAUDE.md). For pipeline, API/auth, storage, integration, deployment, or frontend tasks, start with [current implementation](./docs/CODEMAPS/current-implementation.md) and follow its detail map for the affected area. This file contains only Codex-specific information.

## Platform Differences

- Codex has **skills only** (no slash commands directory)
- Skills are supplied by the runtime skill catalog and local installer; `.codex/skills/` is not a repository source directory.
- Agent client directories and installed skill files (`.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `.agents/`, `.agent/`) are local-only and must not be committed.
- No interactive tools (no AskUserQuestion equivalent) — batch mode only: receives full prompt, returns full response

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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ccas**. Use the GitNexus MCP tools to understand code, assess impact, and navigate safely; the index statistics are intentionally not cached in this file.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze --no-stats --skip-agents-md` in terminal first.

## Recommended Checks

- Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user. Markdown, config, and other non-symbol changes are exempt.
- Before committing, run `gitnexus_detect_changes()` to verify that changes affect only expected symbols and execution flows. This is an advisory check; no repository hook enforces it.
- Warn the user before proceeding when impact analysis returns HIGH or CRITICAL risk.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Safe Navigation

- Use `gitnexus_rename` for symbol renames so references follow the call graph.
- Treat HIGH or CRITICAL impact results as a review gate, not as an informational detail.

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
| Understand architecture / "How does X work?" | `gitnexus-exploring` runtime skill |
| Blast radius / "What breaks if I change X?" | `gitnexus-impact-analysis` runtime skill |
| Trace bugs / "Why is X failing?" | `gitnexus-debugging` runtime skill |
| Rename / extract / split / refactor | `gitnexus-refactoring` runtime skill |
| Tools, resources, schema reference | `gitnexus-guide` runtime skill |
| Index, status, clean, wiki CLI commands | `gitnexus-cli` runtime skill |

<!-- gitnexus:end -->
