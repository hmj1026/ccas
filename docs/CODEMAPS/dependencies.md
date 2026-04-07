<!-- Generated: 2026-04-07 | Files scanned: 94 | Token estimate: ~550 -->

# Dependencies

## External Services

### Gmail API
- **Module**: `ingestor/gmail_client.py`, `ingestor/auth.py`
- **Auth**: OAuth2 (credentials.json + token.json)
- **Usage**: Search emails by bank filter, download PDF attachments
- **Library**: `google-api-python-client`

### Telegram Bot API
- **Module**: `bot/` (10 files, 900 LOC)
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
| fpdf2 | Test PDF generation |
| pymupdf | PDF rendering for tests |
| ruff | Linting + formatting |
| pyright | Type checking |

## Frontend Dependencies

| Package | Purpose |
|---------|---------|
| react 19 | UI framework |
| vite 8 | Build tool |
| @tanstack/react-query 5 | Server state management |
| react-router 7 | Client routing |
| tailwindcss 4.2 | Utility CSS |
| shadcn | UI components |
