# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CCAS (Claude Code Artifact System) is an OpenSpec-based workflow configuration repository. It provides structured, artifact-driven workflows for AI-assisted development across multiple platforms (Claude, Codex, Gemini). There is no compiled code or traditional build system -- this repo contains workflow definitions, skill configurations, and the OpenSpec runtime structure.

## OpenSpec Workflow

The core workflow follows the **spec-driven** schema with this artifact sequence:

```
proposal -> specs -> design -> tasks -> (implementation) -> archive
```

All OpenSpec state lives under `openspec/`:
- `openspec/config.yaml` -- schema selection and optional project context/rules
- `openspec/changes/<name>/` -- active changes with their artifacts
- `openspec/changes/archive/` -- archived changes (prefixed `YYYY-MM-DD-`)
- `openspec/specs/<capability>/spec.md` -- main capability specifications

## Commands

OpenSpec CLI is the primary tool. All commands assume `openspec` is available in PATH.

```bash
# Create a new change
openspec new change "<kebab-case-name>"

# Check artifact status
openspec status --change "<name>"
openspec status --change "<name>" --json

# Get artifact creation instructions
openspec instructions <artifact-id> --change "<name>"

# Get implementation instructions
openspec instructions apply --change "<name>" --json

# List changes and schemas
openspec list --json
openspec schemas --json
```

## Skill Architecture

Ten OpenSpec skills in `.claude/skills/` drive the workflow. Each has a corresponding slash command under `.claude/commands/opsx/`. Equivalent skill definitions exist in `.codex/skills/` and `.gemini/skills/`. Gemini additionally has 3 general-purpose skills (`bug-investigation`, `git-smart-commit`, `software-architecture`) and slash commands under `.gemini/commands/`. Codex has skills only (no commands directory).

| Skill | Slash Command | Purpose |
|-------|---------------|---------|
| openspec-new-change | /opsx:new | Create a change, scaffold directory, show first artifact template |
| openspec-continue-change | /opsx:continue | Create the next artifact in sequence |
| openspec-ff-change | /opsx:ff | Fast-forward: generate all artifacts at once |
| openspec-apply-change | /opsx:apply | Implement tasks from tasks.md |
| openspec-verify-change | /opsx:verify | Three-dimensional verification (completeness, correctness, coherence) |
| openspec-archive-change | /opsx:archive | Finalize and move to archive |
| openspec-sync-specs | /opsx:sync | Merge delta specs into main specs |
| openspec-bulk-archive-change | /opsx:bulk-archive | Archive multiple changes at once |
| openspec-explore | /opsx:explore | Read-only thinking partner mode |
| openspec-onboard | /opsx:onboard | Guided walkthrough of the full workflow |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Database | SQLite (WAL mode) |
| Frontend | React, Vite, TypeScript (planned) |
| Package Manager | uv |
| Testing | pytest + pytest-cov, httpx (ASGI test client) |
| Linting | ruff (check + format), pyright (type check) |
| Integrations | Gmail API (PDF download), Telegram Bot (notifications) |
| Domain | Credit card bill automation (parse PDFs, classify spending, reports) |

## Development Commands

```bash
# Dependencies
uv sync                                    # Install all deps
uv add <pkg>                               # Add runtime dep
uv add --dev <pkg>                         # Add dev dep

# Testing
uv run pytest                              # All tests
uv run pytest --cov --cov-report=term-missing  # With coverage
uv run pytest tests/unit/                  # Unit only
uv run pytest tests/integration/           # Integration only
uv run pytest -x                           # Stop on first failure

# Lint & Format
uv run ruff check .                        # Lint
uv run ruff format .                       # Format
uv run pyright                             # Type check

# Database
uv run alembic upgrade head                # Apply migrations
uv run alembic revision --autogenerate -m "<description>"

# Server
uv run fastapi dev                         # Dev server with hot reload
```

## ECC Agent & Skill Reference

When implementing features in this project, use these ECC agents at the appropriate phase:

| Phase | Agent | Slash Command | When |
|-------|-------|--------------|------|
| Planning | `planner` | `/plan` | Complex features, multi-file changes |
| Architecture | `architect` | -- | System design decisions |
| TDD | `tdd-guide` | `/tdd` | Before writing implementation code |
| Code Review | `python-reviewer` | `/python-review` | After Python code changes |
| Code Review | `code-reviewer` | `/code-review` | After any code changes |
| Security | `security-reviewer` | -- | Auth, user input, API endpoints, secrets |
| Database | `database-reviewer` | -- | SQLAlchemy queries, schema design, migrations |
| Build Fix | `build-error-resolver` | `/build-fix` | Build or type errors |
| Docs | `doc-updater` | `/update-docs` | Documentation updates |

Relevant ECC skills for this project:
- `python-patterns` -- Pythonic idioms, type hints, PEP 8
- `python-testing` -- pytest, TDD, fixtures, mocking, parametrize
- `backend-patterns` -- FastAPI routes, middleware, error handling
- `api-design` -- REST resource naming, status codes, pagination
- `database-migrations` -- Alembic patterns, zero-downtime migrations
- `tdd-workflow` -- RED-GREEN-REFACTOR cycle
- `security-review` -- OWASP Top 10, input validation
- `docker-patterns` -- Docker Compose for local dev

## Key Conventions

- Change names must be **kebab-case** (e.g., `add-user-auth`)
- Skills use `AskUserQuestion` for disambiguation -- never guess when input is ambiguous
- Skills are **not phase-locked**: you can apply tasks before all artifacts are done, or interleave verification with implementation
- Each skill invocation creates at most **one artifact** (except ff-change)
- Task completion is tracked via markdown checkboxes (`- [ ]` / `- [x]`) in the tasks artifact
- Delta specs created during a change sync to `openspec/specs/` at archive time

## Multi-Platform Parity

The 10 OpenSpec skills are defined in three formats:
- `.claude/skills/<name>/SKILL.md` -- Claude Code (markdown with YAML frontmatter)
- `.codex/skills/<name>/SKILL.md` -- Codex (same format, skills only)
- `.gemini/skills/<name>/SKILL.md` -- Gemini (same format)

Slash commands:
- `.claude/commands/opsx/*.md` -- Claude Code commands
- `.gemini/commands/opsx/*.toml` -- Gemini commands (TOML format)
- Codex has no commands directory

When modifying an OpenSpec skill, update all three platform skill definitions to maintain parity.
