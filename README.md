# CCAS — Credit Card Automation System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/hmj1026/ccas?label=release&color=blue)](https://github.com/hmj1026/ccas/releases/latest)

**English** | [繁體中文](README.zh-TW.md)

> An end-to-end pipeline that turns Taiwanese credit card e-statements into a searchable, categorized dashboard — without manual bookkeeping.

CCAS pulls encrypted PDF statements from Gmail, decrypts them with bank-specific passwords, parses each transaction, classifies the spending category, and surfaces the result through a REST API, a React dashboard, and a Telegram bot. It is designed to run on your own machine in Docker Compose — your financial data never leaves your host.

## Features

- **Multi-bank PDF parsing** — CTBC, E.SUN, Taishin, UBOT, Cathay, SinoPac, Fubon (7 parsers, registry-based for easy extension)
- **Gmail OAuth ingestion** — scheduled fetch of statement attachments with idempotent staging
- **Personal categorization rules** — keyword / exact / regex patterns with priority + 100ms regex fail-soft timeout
- **Manual overrides** — edit category / tags / merchant alias per transaction; the pipeline never overwrites manual edits
- **Budgets & reminders** — monthly / per-category / per-bank budgets with 80% & 100% Telegram alerts; per-bill payment reminders
- **Insights** — monthly trends, bank comparisons, year-over-year, top merchants, category deltas
- **Export** — streaming CSV / XLSX with date / bank / category filters
- **Hardened by default** — HMAC-signed session cookies, POST-only login rate limiting, secret-redacting JSON logs, OpenAPI docs disabled in production

## Architecture

```
Gmail ─► staged PDF ─► decrypted PDF ─► Bill + Transaction[] ─► categorized Transaction
                                                │                         │
                                                ▼                         ▼
                                           REST API ──────────► React Dashboard
                                                │
                                                ▼
                                          Telegram Bot  ◄── payment reminders
```

Pipeline stages move PDFs through a state machine: `staged → decrypted → parsed`, with `decrypt_failed` / `parse_failed` retry paths that escalate to `manual_review_needed` after 3 attempts.

## Tech Stack

| Layer | Stack |
|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy (async) + aiosqlite, Alembic, RQ + Redis, APScheduler |
| **Frontend** | React 19, Vite 8, TypeScript 5.9, Tailwind CSS 4, TanStack Query 5, React Router 7, Recharts |
| **PDF / OCR** | pdfplumber, pikepdf, tabula-py, pytesseract, ddddocr (Fubon captcha) |
| **Testing** | pytest (asyncio_mode=auto, cov ≥ 70%), Vitest, Playwright |
| **Lint / Types** | ruff (check + format), pyright, eslint |
| **Infrastructure** | Docker Compose, SQLite (WAL + busy_timeout), Nginx proxy |
| **Package Managers** | uv (backend), pnpm (frontend) |

## Quick Start (Docker)

Requires Docker + Docker Compose. First create a Google Cloud OAuth client — see [`docs/gmail-setup.md`](docs/gmail-setup.md) (Traditional Chinese).

```bash
mkdir ~/ccas && cd ~/ccas
REPO_OWNER=<owner>   # GHCR namespace / GitHub owner (the <owner> in the release URL)
RELEASE=v0.6.0       # pin a released version
curl -fsSL -o docker-compose.yml \
  "https://github.com/${REPO_OWNER}/ccas/releases/download/${RELEASE}/docker-compose.yml"
curl -fsSL -o example.env \
  "https://github.com/${REPO_OWNER}/ccas/releases/download/${RELEASE}/example.env"
cp example.env .env
# Required: REPO_OWNER, CCAS_VERSION, CCAS_PORT, PUBLIC_BASE_URL
# Optional (configurable later via /setup/secrets): Telegram, PDF passwords
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

Then:

1. Read the auto-generated login token: `cat ./data/secrets/api-token`
2. Open `http://localhost:8080/login`, paste the token
3. Visit **Settings** to upload Gmail `credentials.json`, enable banks, and set PDF passwords

Full walkthrough: [`docs/install-quickstart.md`](docs/install-quickstart.md) (Traditional Chinese).

## Local Development

Without Docker — requires Python 3.12+, Node.js 22+, `uv`, and `pnpm`.

```bash
cp .env.example .env
cp config/banks.example.yaml config/banks.yaml
./scripts/setup.sh        # one-time: install deps, Gmail OAuth, alembic upgrade head
./scripts/start.sh        # runs backend (:8000) + frontend (:5173); Ctrl+C stops both
./scripts/dev-test.sh     # backend pytest (in-memory SQLite)
./scripts/dev-lint.sh     # ruff + pyright
```

Frontend-only loop:

```bash
cd frontend && pnpm install && pnpm dev    # http://localhost:5173
pnpm test           # Vitest
pnpm e2e            # Playwright
```

See [`docs/developer-guide.md`](docs/developer-guide.md) for the full toolchain reference (Traditional Chinese).

## Project Structure

```
ccas/
├── backend/           # FastAPI service (src/ccas/{api,ingestor,decryptor,parser,
│                      #   classifier,pipeline,scheduler,bot,storage,tools})
├── frontend/          # React 19 + Vite 8 + TypeScript
├── docker/            # production pull-only compose + nginx proxy image
├── docker-compose.yaml          # dev compose (build from source)
├── docker-compose.override.yml  # dev overrides (bind-mount, hot reload)
├── config/            # banks.yaml, categories.yaml, bank-code-registry.yaml
├── scripts/           # 16 shell scripts: setup, start, lint, test, hooks, ...
├── docs/              # user / developer / deployment / RUNBOOK + CODEMAPS/
├── openspec/          # spec-driven change workflow artifacts
└── .env.example       # environment variable template (SSOT)
```

## Documentation

> All detailed docs are written in **Traditional Chinese**. The English README is a high-level overview; deep dives live in `docs/`.

| Topic | File |
|---|---|
| Install (non-developer) | [`docs/install-quickstart.md`](docs/install-quickstart.md) |
| User guide | [`docs/user-guide.md`](docs/user-guide.md) |
| Developer setup | [`docs/developer-guide.md`](docs/developer-guide.md) |
| Production deployment | [`docs/deployment-guide.md`](docs/deployment-guide.md) |
| Ops runbook | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) |
| Personal rules & budgets | [`docs/personal-rules-and-budgets.md`](docs/personal-rules-and-budgets.md) |
| Gmail OAuth setup | [`docs/gmail-setup.md`](docs/gmail-setup.md) |
| Bank code reference | [`docs/bank-codes.md`](docs/bank-codes.md) |
| Contributing | [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) |

Architecture maps for contributors: [`docs/CODEMAPS/`](docs/CODEMAPS/) — `architecture.md`, `backend.md`, `frontend.md`, `data.md`, `dependencies.md`.

## CI/CD

GitHub Actions on push & PR to `develop` / `master`:

- **backend-lint** — `ruff check` + `ruff format --check` + `pyright`
- **backend-test** — `pytest tests/unit/` with coverage ≥ 70%
- **frontend-lint-test** — `pnpm lint` + `pnpm build` (includes `tsc`) + `pnpm test`

Release pipeline (`release-docker.yaml`) builds and pushes container images to GHCR on tagged releases.

## Contributing

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for branch strategy, Conventional Commits, TDD workflow, and the 80% coverage policy.

## License

Released under the [MIT License](LICENSE) — © 2026 Paul. You are free to use, modify, and distribute this software, provided the copyright notice and license text are retained.
