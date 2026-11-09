# CCAS — Credit Card Automation System

Gmail PDF → decrypt → parse → classify → REST API / Telegram notification.

## On-Demand Skills

| Scenario | Skill |
|---|---|
| OpenSpec spec-driven workflow | `/opsx:*` series |
| Bug root-cause investigation | `dhpk:code-trace` (`diagnose` mode; replaces retired `bug-investigation`) |
| Architecture decisions, module boundaries | `dhpk:dhpk-module-design` (canonical DHPK name; not projected as a local Codex symlink) |
| Free-text task routing (feature/bug/maintenance) | `/dhpk:flow-guide` |
| Feature development workflow | `/dhpk:flow-drive` |

## Agent skills

### Issue tracker

Issues are tracked as GitHub Issues in this repo (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five canonical labels as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`GLOSSARY.md` + `docs/adr/` at repo root, created lazily). Read `GLOSSARY.md` before naming domain concepts, writing issue/test names, or changing business language; read relevant ADRs before changing a recorded decision. See `docs/agents/domain.md` for the routing rules.

### Implementation docs

Read `docs/CODEMAPS/current-implementation.md` when a task touches pipeline flow, API/auth, storage, integrations, deployment, or frontend behavior; follow its linked detail map for that branch. Treat source/config/tests as the final source of truth when the document and repository disagree.

## Key Conventions

- Responses in **Traditional Chinese**
- Branch/change names use **kebab-case** (e.g., `add-user-auth`)
- **CLAUDE.md is SSOT** for project description — do not duplicate
- Resolve material ambiguity using the current runtime’s available clarification tools; preserve prior user decisions

## Skills & External Deps

Skills come from installed Claude plugin manifests (dhpk, openspec/`opsx`, codex, …), surfaced at runtime — they are **not** vendored in this repo. Agent client directories such as `.claude/`, `.codex/`, `.cursor/`, `.gemini/`, and `.agents/` are local-only and intentionally ignored.

Do not vendor or manually sync installed skills or their lock files. Project instructions belong in the root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and versioned `docs/`.

## Code navigation

When exploring code, assessing symbol changes, or preparing a commit, follow
[code navigation and phase isolation](docs/agents/code-navigation.md) for the
GitNexus impact/review gates, evidence reporting, and worktree guidance.
