<!-- Generated: 2026-05-10 | Files scanned: ~95 | Token estimate: ~860 -->

# Dependencies

## External Services

### Gmail API
- **Module**: `ingestor/gmail_client.py`、`ingestor/auth.py`、`api/routers/setup/gmail.py`
- **Auth**: OAuth2（client secret JSON 透過 setup wizard 上傳；token 存 token.json；OAuth state 存 `gmail_oauth_state` 表）
- **Redirect URI**: `gmail_oauth_redirect_uri` dynamic switch（local / docker / prod 三種落點）
- **Library**: `google-api-python-client`

### 銀行網銀 web-fetch
- **Module**: `ingestor/fetcher/` — `base.py`、`captcha.py`、`registry.py`、`banks/fubon/`
- **Usage**: Gmail 未寄送對帳單的銀行（目前 FUBON），改由登入網銀下載 PDF
- **Env**: `FUBON_NATIONAL_ID`、`FUBON_ROC_BIRTHDAY`、`FUBON_CAPTCHA_MAX_RETRIES`、`FUBON_CAPTCHA_FALLBACK_LLM`、`FUBON_CAPTCHA_ARCHIVE_DIR`、`FUBON_MANUAL_STAGING_DIR`
- **Captcha**: ddddocr OCR 為主；失敗後可 fallback 至 Claude Vision（需 `ANTHROPIC_API_KEY`）

### Anthropic API (Claude Vision)
- **Module**: `ingestor/fetcher/banks/fubon/captcha_llm.py`
- **Usage**: FUBON 驗證碼辨識 LLM fallback（`FUBON_CAPTCHA_FALLBACK_LLM=true` 時啟用）
- **Model**: `claude-sonnet-4-6`
- **Library**: `anthropic`（optional extra `fubon-llm`）

### Telegram Bot API
- **Module**: `bot/`（10 files, ~932 LOC）
- **Auth**: Bot token
- **Mode**: Long polling（`Application.run_polling()`）；不需 webhook / 對外 port，未填 token 時 bot 進入 disabled idle
- **Commands**: `/status`、`/upcoming`、`/summary`、`/category`、`/paid`
- **Push**: 新帳單通知、付款提醒（依 `reminder_settings.days_before` 觸發）、預算超標警示
- **Library**: `python-telegram-bot`

### Redis + RQ
- **Usage**: pipeline job queue（RQ 2.x）+ APScheduler 共用
- **Config**: `maxmemory 256mb`、`allkeys-lru` eviction、`appendonly yes`
- **Worker command**: `uv run rq worker --url $REDIS_URL`（rq 2.x 已移除 `--quiet`，改用 `info --raw -Q` 做 healthcheck）
- **Library**: `redis`、`rq`

## Docker Compose Services

```
backend    port 8000 (127.0.0.1, dev only)，volumes: /data /config /logs，alembic + seed bootstrap
worker     RQ worker，volumes: /data /config /logs，SKIP_DB_BOOTSTRAP=1
scheduler  APScheduler，volumes: /data /config /logs，SCHEDULER_HEARTBEAT_PATH=/data/scheduler-heartbeat
bot        Telegram bot (long polling)，volumes: /data /config /logs
frontend   nginx static (dev: 8080)，depends: backend
proxy      nginx reverse proxy (prod: ${CCAS_PORT:-8080})，/api → backend、/ → frontend
redis      port 6379 (127.0.0.1)，named volume: ccas-redis (dev) / bind mount (prod)
```

**Healthchecks**（compose-pull-deploy 修復）：
- `worker`：`uv run rq info -u $REDIS_URL --raw -Q`（確認 redis 可達 + rq runtime 正常）
- `scheduler`：`test -f /data/scheduler-heartbeat && find … -mmin -1`（heartbeat 60s 內須更新；scheduler 主程式週期寫入）

**dev-tools profile**（`docker compose --profile dev-tools up`）：
```
sqlite-web       SQLite browser (read-only), port 8088
redis-commander  Redis key browser, port 8081
```

## Runtime Requirements

- **Python**: 3.12+（`backend/pyproject.toml: requires-python = ">=3.12"`）
- **Node**: 22+（CI matrix + `.nvmrc`）
- **pnpm**: 9.15.9+

## System Dependencies

| Package | Purpose |
|---------|---------|
| tesseract-ocr | OCR engine (system binary) |
| tesseract-ocr-chi-tra | Traditional Chinese language support for OCR |

Both dev 與 production Docker stage 都安裝（見 `backend/Dockerfile`）。本機開發：
```bash
# macOS
brew install tesseract tesseract-lang
# Ubuntu/Debian
apt-get install tesseract-ocr tesseract-ocr-chi-tra
```

## Key Python Dependencies

| Package | Purpose |
|---------|---------|
| fastapi | REST API framework |
| sqlalchemy[asyncio] | ORM (async) |
| alembic | DB migrations |
| pydantic-settings | Environment config |
| pdfplumber | PDF table extraction |
| pikepdf | PDF decryption |
| pytesseract | OCR fallback（依賴 tesseract system package） |
| tabula-py | PDF table extraction (alt) |
| httpx | Async HTTP client |
| apscheduler | Cron scheduling |
| rq | Redis job queue（2.x） |
| openpyxl | XLSX export 產出（exports.py） |
| cryptography | bank_secrets 對稱加密 |

## Dev Dependencies

| Package | Purpose |
|---------|---------|
| pytest + pytest-cov | Testing（80% coverage min） |
| pytest-timeout | Integration test timeout guard |
| fpdf2 | Test PDF generation |
| pymupdf | PDF rendering for tests |
| ruff | Linting + formatting |
| pyright | Type checking |

## Backend Utility Scripts

`backend/scripts/` — 非 production，手動執行的維運/開發工具：

| Script | Purpose |
|--------|---------|
| `seed.py` | 匯入測試資料 |
| `migrate_staging_paths.py` | 將 staged_path 由絕對路徑遷移至相對路徑 |
| `eval_captcha.py` | FUBON 驗證碼 OCR 正確率評估 |
| `harvest_captcha.py` | 收集真實驗證碼樣本供 eval 資料集 |
| `dedupe_staged_attachments.py` | 清理重複 staged_attachments |
| `reimport.py` | 強制重新匯入特定帳單 |

## Frontend Dependencies

| Package | Purpose |
|---------|---------|
| react 19 | UI framework |
| vite 8 | Build tool |
| @tanstack/react-query 5 | Server state management（pipeline runs polling） |
| react-router 7 | Client routing |
| tailwindcss 4.2 | Utility CSS |
| shadcn | UI components |
| recharts | Insights / comparison-chart 折線/柱狀圖 |

## Release / Deployment

- **Image**: `ghcr.io/${REPO_OWNER}/ccas-backend:${CCAS_VERSION:-release}`
- **CCAS_VERSION**: 受 release blocker regex 限制（路徑 D §13.9）；suffix 須符合驗證
- **GitHub Actions**: release artifact upload 已修（commit `0322afe`），支援 release 觸發 build + push
- **SSOT Sync Pairs**: `scripts/docker-entrypoint.sh`、`scripts/check-env.sh`、`.env.example`、`config/*.example.yaml`，修改後須跑 `./scripts/sync-docker-image-assets.sh`
