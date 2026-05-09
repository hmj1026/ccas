---
name: ccas-dev-commands
description: "CCAS 專案日常開發指令參考（Local 與 Docker 兩種環境）。使用時機：當使用者詢問如何執行測試、lint、pipeline、server、alembic 遷移、seed、env 驗證、git hooks 等日常指令；或 agent 準備執行這些指令但不確定正確寫法時。包含路徑慣例（從專案根目錄執行）與環境選擇原則（開發者用 Local、QA 用 Docker）。"
---

# CCAS 開發指令參考

## 環境選擇原則

- **開發者（含 AI agent）→ Local 指令**（預設）
- **QA 測試 → Docker 指令**（含 tesseract OCR）
- 所有本地指令從**專案根目錄**執行，無需 `cd backend`

---

## Local — 開發者日常（預設）

測試使用 in-memory SQLite，不需 Docker、tesseract 或 Redis。

### Testing

```bash
./scripts/dev-test.sh                      # All tests
./scripts/dev-test.sh tests/unit/ -v       # Unit only
./scripts/dev-test.sh tests/integration/   # Integration only
./scripts/dev-test.sh --cov --cov-report=term-missing  # With coverage
./scripts/dev-test.sh -x                   # Stop on first failure
```

### Lint & Format

```bash
./scripts/dev-lint.sh                      # ruff check + format + pyright
```

### Dependencies（需 cd backend）

```bash
cd backend && uv sync                      # Install all deps
cd backend && uv add <pkg>                 # Add runtime dep
cd backend && uv add --dev <pkg>           # Add dev dep
```

### Database（需 cd backend）

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run alembic revision --autogenerate -m "<description>"
```

### Pipeline（本地無 tesseract 時 OCR 自動略過）

```bash
cd backend && uv run python -m ccas.pipeline --bank CTBC
cd backend && uv run python -m ccas.pipeline --force --bank CTBC --year 2026 --month 3
cd backend && uv run python -m ccas.pipeline --from parse --to classify
```

### Server

```bash
./scripts/start.sh                         # Backend + frontend
cd backend && uv run uvicorn ccas.api.app:create_app --factory --reload
```

### Seed Data

```bash
cd backend && uv run python scripts/seed.py             # Add test data
cd backend && uv run python scripts/seed.py --reset     # Reset and re-seed
```

### Env Validation

```bash
./scripts/check-env.sh                    # Check .env for missing vars
```

### Git Hooks (Pre-CI)

```bash
./scripts/setup-hooks.sh                  # Install pre-commit + pre-push hooks
./scripts/pre-push.sh                     # Manually run full CI-equivalent checks
RUN_FRONTEND=0 ./scripts/pre-push.sh      # Backend checks only
RUN_BACKEND=0 ./scripts/pre-push.sh       # Frontend checks only
```

> **Git Hooks**：`setup.sh` 會自動安裝 hooks。pre-commit 檢查 staged 檔案的 lint（< 10s），pre-push 執行完整 CI 鏡像檢查。緊急繞過：`git commit --no-verify` / `git push --no-verify`。

---

## Docker — QA 測試（含 tesseract OCR）

需先啟動容器：`docker compose up --build`

```bash
docker compose up --build                  # Start all services
./scripts/test.sh                          # Run all tests in Docker
./scripts/test.sh tests/unit/ -v           # Unit tests only
./scripts/pipeline.sh --bank CTBC          # Run pipeline (with OCR)
./scripts/pipeline.sh --from parse --force # Pipeline with stage control
```

> **注意**：`scripts/test.sh` 和 `scripts/pipeline.sh` 使用 `docker compose exec`，若容器未啟動會報錯。詳見 `docs/qa-testing-guide.md`。
