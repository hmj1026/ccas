# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CCAS (Credit Card Automation System) is a credit card bill automation pipeline. It ingests PDF statements from Gmail, decrypts and parses them, classifies spending, and exposes results via a REST API dashboard and Telegram notifications. The project uses OpenSpec for spec-driven development across multiple AI platforms (Claude, Codex, Gemini).

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

The repo defines 12 skills in `.claude/skills/`: 10 OpenSpec workflow skills (each with a corresponding slash command under `.claude/commands/opsx/`) and 2 general-purpose skills (`bug-investigation`, `software-architecture`). Equivalent OpenSpec skill definitions exist in `.codex/skills/` and `.gemini/skills/`; Gemini additionally has the repo-local `git-smart-commit` skill. ECC reference skills (python-patterns, tdd-workflow, etc.) are available globally via the `everything-claude-code` plugin -- they are not installed locally.

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
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Package Manager | uv |
| Testing | pytest + pytest-cov, httpx (ASGI test client) |
| Linting | ruff (check + format), pyright (type check) |
| Integrations | Gmail API (PDF download), Telegram Bot (notifications) |
| Domain | Credit card bill automation (parse PDFs, classify spending, reports) |

## Development Commands

> **環境選擇**：開發者（含 AI agent）使用 Local 指令；QA 測試使用 Docker 指令。
> 所有本地指令從**專案根目錄**執行，無需 `cd backend`。

### Local — 開發者日常（預設）

測試使用 in-memory SQLite，不需 Docker、tesseract 或 Redis。

```bash
# Testing
./scripts/dev-test.sh                      # All tests
./scripts/dev-test.sh tests/unit/ -v       # Unit only
./scripts/dev-test.sh tests/integration/   # Integration only
./scripts/dev-test.sh --cov --cov-report=term-missing  # With coverage
./scripts/dev-test.sh -x                   # Stop on first failure

# Lint & Format
./scripts/dev-lint.sh                      # ruff check + format + pyright

# Dependencies (需 cd backend)
cd backend && uv sync                      # Install all deps
cd backend && uv add <pkg>                 # Add runtime dep
cd backend && uv add --dev <pkg>           # Add dev dep

# Database (需 cd backend)
cd backend && uv run alembic upgrade head
cd backend && uv run alembic revision --autogenerate -m "<description>"

# Pipeline (本地無 tesseract 時 OCR 自動略過)
cd backend && uv run python -m ccas.pipeline --bank CTBC
cd backend && uv run python -m ccas.pipeline --force --bank CTBC --year 2026 --month 3
cd backend && uv run python -m ccas.pipeline --from parse --to classify

# Server
./scripts/start.sh                         # Backend + frontend
cd backend && uv run uvicorn ccas.api.app:create_app --factory --reload

# Seed Data
cd backend && uv run python scripts/seed.py             # Add test data
cd backend && uv run python scripts/seed.py --reset     # Reset and re-seed

# Env Validation
./scripts/check-env.sh                    # Check .env for missing vars

# Git Hooks (Pre-CI)
./scripts/setup-hooks.sh                  # Install pre-commit + pre-push hooks
./scripts/pre-push.sh                     # Manually run full CI-equivalent checks
RUN_FRONTEND=0 ./scripts/pre-push.sh     # Backend checks only
RUN_BACKEND=0 ./scripts/pre-push.sh      # Frontend checks only
```

> **Git Hooks**: `setup.sh` 會自動安裝 hooks。pre-commit 檢查 staged 檔案的 lint（< 10s），
> pre-push 執行完整 CI 鏡像檢查。緊急繞過：`git commit --no-verify` / `git push --no-verify`。

### Docker — QA 測試（含 tesseract OCR）

需先啟動容器：`docker compose up --build`

```bash
docker compose up --build                  # Start all services
./scripts/test.sh                          # Run all tests in Docker
./scripts/test.sh tests/unit/ -v           # Unit tests only
./scripts/pipeline.sh --bank CTBC          # Run pipeline (with OCR)
./scripts/pipeline.sh --from parse --force # Pipeline with stage control
```

> **注意**：`scripts/test.sh` 和 `scripts/pipeline.sh` 使用 `docker compose exec`，
> 若容器未啟動會報錯。詳見 [QA 測試指南](docs/qa-testing-guide.md)。

## ECC Agent & Skill Reference

See `.claude/rules/execution-policy.md` for the full agent roster, mandatory post-steps, and task routing. Key agents: `python-reviewer`, `tdd-guide`, `database-reviewer`, `security-reviewer`.

## Environment Configuration

A single `.env` file at the **project root** is shared by backend and frontend:
- Backend: `pydantic-settings` loads `../.env` relative to `backend/` working directory
- Frontend: Vite dev server proxies `/api` to `http://127.0.0.1:8000` (configured in `vite.config.ts`); no `VITE_API_BASE` needed for development
- Docker: `docker-compose.yaml` injects via `env_file: ./.env`
- Template: `.env.example` documents all available variables

## Key Conventions

- All responses must be in **Traditional Chinese** (正體中文)
- Change names must be **kebab-case** (e.g., `add-user-auth`)
- **CLAUDE.md is the SSOT** (single source of truth) for project context; `AGENTS.md` and `GEMINI.md` contain only platform-specific differences
- Skills use `AskUserQuestion` for disambiguation -- never guess when input is ambiguous
- Skills are **not phase-locked**: you can apply tasks before all artifacts are done, or interleave verification with implementation
- Each skill invocation creates at most **one artifact** (except ff-change)
- Task completion is tracked via markdown checkboxes (`- [ ]` / `- [x]`) in the tasks artifact
- Delta specs created during a change sync to `openspec/specs/` at archive time

## Multi-Platform Parity

When modifying an OpenSpec skill, update all three platforms: `.claude/skills/`, `.codex/skills/`, `.gemini/skills/`. See `.claude/rules/skill-parity.md` for full details.
