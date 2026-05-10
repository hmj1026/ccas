<!-- Generated: 2026-05-10 | Files scanned: ~130 | Token estimate: ~1180 -->

# Backend

## API Routes

All under `/api`, require Bearer token auth (except `/health` and Setup OAuth callback).
Mounted in `api/app.py:create_app()` via `include_router(...)`。

```
Auth (auth.py):
  GET    /api/auth/session
  POST   /api/auth/session
  DELETE /api/auth/session

Dashboard (overview.py):
  GET    /api/overview

Bills (bills.py):
  GET    /api/bills                       (list + paginate)
  PATCH  /api/bills/{id}                  (mark paid)
  GET    /api/bills/{id}/transactions     (inline transaction list)
  GET    /api/bills/{id}/pdf              (download)

Transactions (transactions.py):
  GET    /api/transactions                (filter, paginate, sort)

Transaction Edit (transactions_edit.py):
  GET    /api/transactions/{id}                       (detail)
  PUT    /api/transactions/{id}                       (edit category/note/tags/alias → manual_override)
  POST   /api/transactions/{id}/note
  DELETE /api/transactions/{id}/manual-override       (revert to auto-classify)

Exports (exports.py):
  GET    /api/transactions/export         (CSV / Excel — XLSX via openpyxl)

Analytics v1 (analytics.py):
  GET    /api/analytics/years
  GET    /api/analytics/trend
  GET    /api/analytics/categories
  GET    /api/analytics/banks

Analytics v2 (analytics_v2.py — Insights 頁):
  GET    /api/analytics/compare/banks
  GET    /api/analytics/compare/years
  GET    /api/analytics/top-merchants

Settings (settings.py):
  GET    /api/settings/banks
  POST   /api/settings/banks
  PATCH  /api/settings/banks/{id}
  GET    /api/settings/categories
  POST   /api/settings/categories
  PATCH  /api/settings/categories/{id}
  DELETE /api/settings/categories/{id}

Pipeline (pipeline.py):
  POST   /api/pipeline/trigger             (推入 RQ queue → 回傳 run_id)
  GET    /api/pipeline/runs                (status filter + limit ≤100)
  GET    /api/pipeline/runs/{run_id}       (含 stage_summary 詳情)

Rules (rules.py):
  GET    /api/rules                        (filter by enabled)
  POST   /api/rules
  PUT    /api/rules/{id}
  DELETE /api/rules/{id}
  POST   /api/rules/test                   (dry-run pattern + sample matches)

Reminders (reminders_settings.py):
  GET    /api/reminders/settings
  PUT    /api/reminders/{bill_id}/settings (days_before / channel / enabled)
  POST   /api/reminders/{bill_id}/test     (寄送測試訊息)

Budgets (budgets.py):
  GET    /api/budgets                              (list, scope filter)
  POST   /api/budgets
  PUT    /api/budgets/{id}
  DELETE /api/budgets/{id}
  GET    /api/budgets/alerts/active
  POST   /api/budgets/alerts/{id}/acknowledge
  GET    /api/budgets/{id}/current-period          (本期消費 vs 上限)

Staged Attachments (staged_attachments.py):
  GET    /api/staged-attachments           (失敗附件 + status filter)

Setup — Gmail OAuth (setup/gmail.py):
  POST   /api/setup/gmail/credentials      (上傳 client secret JSON)
  GET    /api/setup/gmail/authorize        (取得授權 URL)
  GET    /api/setup/gmail/callback         (OAuth code → token)，無需 Bearer
  GET    /api/setup/gmail/status
  POST   /api/setup/gmail/revoke

Setup — Banks (setup/banks.py):
  GET    /api/setup/banks                  (含 enabled / display_name)
  PUT    /api/setup/banks/{code}

Setup — Bank Secrets (setup/secrets.py):
  GET    /api/setup/secrets                (僅回傳是否已設定)
  PUT    /api/setup/secrets/{code}         (寫入加密的 PDF 密碼)
  DELETE /api/setup/secrets/{code}
  POST   /api/setup/secrets/import-from-env

Setup — Admin Token (setup/admin.py):
  GET    /api/setup/admin/token-info       (rotate 時間 / 版本)
  POST   /api/setup/admin/token-rotate

Health:
  GET    /health                           (no auth)
```

## Pipeline Stages

`run_pipeline()` in `pipeline/orchestrator.py` 由 RQ worker 執行；progress 透過 `pipeline/progress.py:stage_finished()` 寫入 `PipelineRun.stage_summary`（含 counts + errors），前端 `operations.tsx` 輪詢顯示。
支援 `--from`/`--to` stage range via `PipelineOptions`。

| # | Stage | Module | Key File |
|---|-------|--------|----------|
| 1 | Ingest | `ingestor/` | `job.py`, `gmail_client.py`, `fetcher/`（FUBON web-fetch + captcha） |
| 2 | Decrypt | `decryptor/` | `job.py`, `decrypt.py`；staged_path 以 STAGING_DIR 相對路徑儲存 |
| 3 | Parse | `parser/` | `job.py`, `registry.py`, `banks/{ctbc,esun,taishin,ubot,cathay,sinopac,fubon}_v1.py`, `ocr.py` fallback |
| 4 | Classify | `classifier/` | `job.py`, `engine.py`（先匹配使用者 ClassificationRule，未命中再 keyword） |
| 5 | Notify | `bot/` | `notifications.py`, `job.py`（auto-query is_notified=False） |

## Configuration (config.py Settings)

| Group | Key Fields |
|-------|-----------|
| Database | `database_url`, `staging_dir` |
| Gmail | `gmail_credentials_path`, `gmail_token_path`, `gmail_oauth_redirect_uri`（dynamic switch） |
| Telegram | `telegram_bot_token`, `telegram_chat_id`, `telegram_allowed_chat_ids` |
| API | `api_token`, `api_host`, `api_port`, `api_session_cookie_name`, `api_session_max_age`, `api_cookie_secure`, `frontend_origins`, `admin_token_*` |
| Redis / Queue | `redis_url`（default `redis://localhost:6379/0`） |
| Scheduler | `scheduler_api_base_url`, `scheduler_heartbeat_path`（default `/data/scheduler-heartbeat`） |
| FUBON Fetcher | `fubon_national_id`, `fubon_roc_birthday`, `fubon_captcha_max_retries`, `fubon_captcha_fallback_llm`, `fubon_captcha_archive_dir`, `fubon_manual_staging_dir` |
| Anthropic | `anthropic_api_key`（SecretStr，僅 captcha LLM fallback 啟用時需要） |
| Logging | `log_level`, `log_format`, `log_dir`, `log_file_max_bytes`, `log_file_backup_count`, `log_file_prefix` |
| PDF Passwords | `get_pdf_password(bank_code)` → 讀 `bank_secrets` 表（fallback `PDF_PASSWORD_{BANK_CODE}`） |

## Module Inventory

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| api | 20 | ~3060 | FastAPI routes（16 routers，含 setup/）、schemas、deps、security headers |
| parser | 17 | ~4604 | 7 bank parsers + registry + OCR fallback |
| ingestor | 18 | ~2337 | Gmail download + staging；fetcher（FUBON web-fetch + captcha） |
| bot | 10 | ~932 | Telegram commands、notifications、reminder dispatch |
| pipeline | 8 | ~870 | Orchestrator + progress（stage_finished）+ CLI + worker glue |
| tools | 4 | ~773 | Bank configs YAML、Gmail auth helpers、reclassify utility |
| classifier | 5 | ~410 | Engine：user-rule 優先 + keyword fallback |
| decryptor | 5 | ~386 | PDF password resolution；staged_path 相對路徑 |
| storage | 5 | ~340 | ORM models（含 PipelineRun / Budget / ClassificationRule …）+ async session |
| scheduler | 5 | ~310 | APScheduler cron + heartbeat writer + reminder dispatch |
| core | 4 | ~475 | config / errors / log / __init__ |
| **Total** | **~130** | **~14500** | |
