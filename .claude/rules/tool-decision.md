# Tool Decision Guide: GitNexus / cx / claude-mem

## Cost Gradient (prefer cheaper tools first)

```
claude-mem read  →  cx  →  GitNexus MCP  →  Read tool (full file)
```

---

## Decision Table

| Scenario | Preferred Tool | Notes |
|------|----------|------|
| Find symbol definition / get old text for Edit | `cx definition --name X` | Fall back to Grep → Read if cx fails |
| Find symbol callers / references (known scope) | `cx references --name X` | Use GitNexus for cross-module or execution flow needs |
| Explore unfamiliar code (have concept keyword) | `gitnexus_query` | Returns process-grouped results |
| Explore directory structure (have path intuition) | `cx overview DIR` | Compatible with gitnexus_query, can combine |
| Full symbol context (caller + callee + flow membership) | `gitnexus_context` | Deeper than cx references |
| Re-orient after context compression | `cx overview` / `cx definition` | Never re-read full files |
| Before editing a function / class / method | `gitnexus_impact` (MUST) | See exemption table below |
| Rename a symbol | `gitnexus_rename` | Never use find-and-replace |
| Verify scope before committing | `gitnexus_detect_changes` (MUST) | No exemptions |

---

## gitnexus_impact Exemption Boundary

| Change Type | Requires impact? |
|----------|----------------|
| Function / class / method (any size) | **MUST** (no exemption) |
| Config / Markdown / .env (non-symbol) | Exempt |
| Test file assertion tweak (no signature change) | Exempt |
| Docstring / type annotation only | Exempt (but public API types need impact) |

---

## claude-mem Storage Decision

**Save when any of these apply:**
- User explicitly asks to remember
- User correction ("don't do that", "wrong, it should be…")
- User confirms a non-obvious approach ("yes exactly", "great, keep doing that")
- Non-obvious project decision (not derivable from code or git)

**Do not save when any of these apply:**
- Derivable from current code
- Derivable from git log / blame
- Only valid for the current session (transient state)
- Already documented in CLAUDE.md or other rules files
