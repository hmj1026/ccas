# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ccas**. Use the GitNexus MCP tools to understand code, assess impact, and navigate safely; index statistics are intentionally not cached in this file.

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

## Evidence presentation

Present risk, direct callers, affected processes, and unresolved limits first.
Keep complete tool output in a temporary artifact when needed; inspect relevant
details without dumping the entire graph into the conversation. Summary counts
do not replace the full impact check. Treat UNKNOWN, partial, or truncated
results as unresolved and disclose fallback evidence.

## Phase isolation

Keep independent implementation phases in separate worktrees, or finish and
commit the current phase before introducing the next phase's tests. The hook
checks the full backend with pyright; unrelated unfinished tests still affect
that check. Auto-fix covers staged Python files only and stops when those files
also contain unstaged changes, preserving the index/worktree boundary.

## Repository precommit runner

`precommit.config.json` declares the existing backend/frontend commands for the
updated dhpk precommit runner. Its `lint_fix` stage uses the repository's
read-only lint/type checks; full mode also builds the frontend. Fast mode skips
that build. Native Git hooks and CI retain their own additional gates.

Use a dhpk runner with repository-config support. An older installed runner
that reports no steps has not verified this project; update through the normal
dhpk installer rather than copying skill files into this checkout.
