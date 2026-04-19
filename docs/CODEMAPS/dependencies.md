<!-- Generated: 2026-04-19 | Files scanned: ~90 | Token estimate: ~680 -->

# Dependencies

## External Services

### Gmail API
- **Module**: `ingestor/gmail_client.py`, `ingestor/auth.py`
- **Auth**: OAuth2 (credentials.json + token.json)
- **Usage**: Search emails by bank filter, download PDF attachments
- **Library**: `google-api-python-client`

### 銀行網銀 web-fetch
- **Module**: `ingestor/fetcher/` — `base.py`, `captcha.py`, `registry.py`, `banks/fubon/` (directory)
- **Usage**: Gmail 未寄送對帳單的銀行，改由登入網銀下載 PDF
- **Env**: `FUBON_NATIONAL_ID`, `FUBON_ROC_BIRTHDAY`, `FUBON_CAPTCHA_MAX_RETRIES`, `FUBON_CAPTCHA_FALLBACK_LLM`, `FUBON_CAPTCHA_ARCHIVE_DIR`, `FUBON_MANUAL_STAGING_DIR`
- **Captcha**: ddddocr OCR 為主；失敗後可 fallback 至 Claude Vision（需 `ANTHROPIC_API_KEY`）

### Anthropic API (Claude Vision)
- **Module**: `ingestor/fetcher/banks/fubon/captcha_llm.py`
- **Usage**: FUBON 驗證碼辨識 LLM fallback（`FUBON_CAPTCHA_FALLBACK_LLM=true` 時啟用）
- **Model**: `claude-sonnet-4-6`
- **Library**: `anthropic` (optional extra `fubon-llm`)

### Telegram Bot API
- **Module**: `bot/` (10 files, ~932 LOC)
- **Auth**: Bot token
- **Commands**: `/status`, `/upcoming`, `/summary`, `/category`, `/paid`
- **Push**: New bill notifications, payment reminders
- **Library**: `python-telegram-bot`

### Redis
- **Usage**: RQ job queue (pipeline) + APScheduler backend
- **Config**: `maxmemory 256mb`, `allkeys-lru` eviction, `appendonly yes`
- **Library**: `redis`

## Docker Compose Services

```
backend    port 8000 (127.0.0.1), volumes: /data /logs /scripts
worker     RQ worker, volumes: /data /logs (depends: backend, redis)
scheduler  APScheduler cron, volumes: /data /logs (depends: redis)
bot        Telegram bot, volumes: /data /logs (depends: redis)
frontend   nginx static, port 8080 (127.0.0.1) (depends: backend)
redis      port 6379 (127.0.0.1), named volume: ccas-redis
```

**dev-tools profile** (`docker compose --profile dev-tools up`):
```
sqlite-web       SQLite browser (read-only), port 8088
redis-commander  Redis key browser, port 8081
```

## System Dependencies

| Package | Purpose |
|---------|---------|
| tesseract-ocr | OCR engine (system binary) |
| tesseract-ocr-chi-tra | Traditional Chinese language support for OCR |

**Note:** Both dev and production Docker stages install these system packages (see `backend/Dockerfile`). For local development, install via:
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
| pytesseract | OCR fallback for image-based PDFs (requires tesseract system package) |
| tabula-py | PDF table extraction (alt) |
| httpx | Async HTTP client |
| apscheduler | Job scheduling |
| rq | Background job queue |

## Dev Dependencies

| Package | Purpose |
|---------|---------|
| pytest + pytest-cov | Testing (80% coverage min) |
| pytest-timeout | Integration test timeout guard (e.g., `--timeout=120`) |
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
| @tanstack/react-query 5 | Server state management |
| react-router 7 | Client routing |
| tailwindcss 4.2 | Utility CSS |
| shadcn | UI components |
