<!-- Verified: 2026-09-12 | Sources: source tree, tests, compose files, GitNexus -->

# 目前實作總覽（As-built）

本文件描述目前程式碼實際提供的行為，作為後續功能規劃與文件維護的入口。需求意圖請看 `openspec/specs/`；部署操作請看 `docs/deployment-guide.md` 與 `docs/RUNBOOK.md`。

> 文件界線：本文件記錄 runtime 的 as-built 行為；`openspec/specs/` 記錄需求與
> 已接受的設計，可能保留歷史命名。規劃新變更時，先將相關 spec 與 source、tests
> 對照；若契約不同，先確認要延續 runtime 或修正 spec，再建立下一個 change。

## 1. 系統責任分布

CCAS 是一個以 SQLite 為資料來源、以 Redis/RQ 執行非同步工作、由 React 前端與 Telegram 提供讀取入口的信用卡帳單自動化系統。

```text
                         ┌──────────────────────┐
                         │   React SPA / 瀏覽器   │
                         │  login、dashboard、設定 │
                         └──────────┬───────────┘
                                    │ HTTP + session cookie
                                    v
┌─────────────┐   ┌─────────────┐  ┌──────────────────────┐
│ Gmail API   │──>│             │  │ FastAPI backend      │
└─────────────┘   │             │  │ /api、health、setup │
┌─────────────┐   │  Ingestor   │  └──────────┬───────────┘
│ 銀行網銀     │──>│             │             │ enqueue / query
│ 目前 FUBON   │   └──────┬──────┘             v
└─────────────┘          │             ┌─────────────┐
                         v             │ Redis / RQ  │
                  staged attachment   └──────┬──────┘
                                               v
                                      ┌─────────────────┐
                                      │ RQ worker       │
                                      │ 五階段 pipeline │
                                      └────────┬────────┘
                                               │
                  ┌────────────────────────────┼────────────────────────────┐
                  v                            v                            v
             SQLite DB                  staged PDF files             Telegram API
       Bill / Transaction / rules       /data/staging                 push / bot
```

### Runtime entry points

| Runtime | 入口 | 責任 |
|---|---|---|
| Backend | `ccas.api.app:create_app` | FastAPI、認證、業務 API、setup API、health/readiness |
| Worker | `ccas.pipeline.worker:run_pipeline_sync` | RQ 同步工作入口，建立 async session，執行 pipeline 並持久化 run 終態 |
| Pipeline CLI | `python -m ccas.pipeline` | 直接執行 pipeline；使用 `NoopProgressReporter`，不建立 `pipeline_runs` |
| Scheduler | `python -m ccas.scheduler` | 每日觸發 pipeline、付款提醒、預算評估；每 30 秒寫 heartbeat |
| Telegram bot | `python -m ccas.bot` | long polling、白名單指令、查詢與標記帳單已繳 |
| Agent CLI | `ccas-agent` / `python -m ccas.cli` | 唯讀 agent 查詢，JSON/table 輸出 |
| Agent MCP | `ccas-mcp` / `python -m ccas.mcp` | 官方 MCP SDK stdio 唯讀工具介面 |
| Frontend | Vite dev / Nginx production | React Router、React Query、頁面與設定中心 |

Docker Compose 將 backend、worker、scheduler、bot、frontend、redis 分開執行；production pull-only compose 另外以 proxy 統一對外暴露入口。

Scheduler 的固定工作為：每日 00:00 觸發 pipeline、每日 02:00 評估預算、每日
09:00 發送付款提醒；另有每 30 秒更新一次的 heartbeat。每日工作允許最多延遲
一小時執行，單一工作不允許重疊；heartbeat 的 misfire grace 為 15 秒。

## 2. 主要資料流程

```text
帳單來源
  └─> ingest：找郵件／網銀連結、下載 PDF、寫入 staged_attachments
        └─> decrypt：解析銀行密碼，必要時產生解密檔
              └─> parse：選擇銀行 parser，產生 Bill + Transaction
                    └─> classify：套用手動覆寫保護、使用者規則、內建關鍵字
                          └─> notify：對尚未通知的 Bill 發 Telegram
```

`run_pipeline()` 固定依序執行 `ingest → decrypt → parse → classify → notify`。每個 stage 以獨立 job 負責自己的資料查詢、逐項處理與摘要，orchestrator 只負責順序、stage 範圍、錯誤隔離與摘要彙整。

### Pipeline stage 契約

| Stage | 輸入與主要行為 | 成功結果 | 失敗／重試語意 | 主要實作 |
|---|---|---|---|---|
| ingest | 查詢啟用銀行；搜尋 Gmail PDF 或符合條件的 FUBON web-fetch 郵件；以 message/part 去重後下載 | `staged_attachments.status=staged` | 單附件失敗記為 `failed`；失效 serial key 記為 `fetch_expired`；每項目提交 | `ingestor/job.py`, `gmail_client.py`, `fetcher/` |
| decrypt | 取 `staged` 附件，依銀行解析 DB 密碼與 env fallback；未加密 PDF 直接透通 | `decrypted` | 單附件失敗記為 `decrypt_failed`；每銀行只解析一次密碼，逐項提交 | `decryptor/job.py`, `decrypt.py`, `password.py` |
| parse | 取 `decrypted` 附件；依 bank code 與 active parser version 嘗試候選 parser；必要時使用 OCR | 建立 `Bill` 與 `Transaction`，附件成為 `parsed` | 單附件失敗記為 `parse_failed`；零額歷史帳單為 `parse_skipped`；單項提交；`force` 可刪除同銀行同月份舊 Bill 重建 | `parser/intake.py`, `parser/registry.py`, `parser/banks/*_vN.py` |
| classify | 取未分類交易；保留手動覆寫；依 user rules 再走內建 keyword engine | 寫入 category；回傳 user/engine/default 統計 | 整批寫入為 all-or-nothing；flush/commit 失敗會 rollback 並使 stage 失敗 | `classifier/job.py`, `engine.py`, `user_rules.py` |
| notify | 查詢 `is_notified=false` 的 Bill；先 claim `PaymentReminder(bill_id, new_bill)` 再送 Telegram | 成功後設 `Bill.is_notified=true` | 缺 Telegram 設定時跳過；單筆失敗記錄並繼續；claim 保護重複送出 | `bot/job.py`, `bot/notifications.py` |

每個 stage crash 都會被 `_run_stage()` 轉為 `StageSummary`，後續 stage 仍會執行。ingest/decrypt/parse 的已提交項目會保留；RQ job 若達到重試上限，worker 會把仍處於 `staged` 或 `decrypted` 的項目標為 `manual_review_needed`。

## 3. Pipeline 執行生命週期

### API / Scheduler 路徑

1. API router 或 scheduler 建立 `PipelineRun(status=queued)`。
2. 將 `run_pipeline_sync` enqueue 至 Redis/RQ，回填 RQ job id。
3. worker 以 `DbLifecycleStore` 將 run 標為 `running`。
4. `run_pipeline_sync` 在組裝點注入 `run_notify_job`，呼叫與 bot 解耦的 `run_pipeline()`。
5. `DbProgressReporter` 以短生命週期 session 寫入目前 stage 與 `stage_summary`；item progress 以 250ms 節流，stage finish 立即 flush 並對 SQLite lock 重試三次。
6. `RunLifecycle` 根據 stage errors 與 classify rollback 判定 `succeeded` 或 `failed`，再由 `DbLifecycleStore` 寫回終態。
7. `/operations` 前端輪詢 `/api/pipeline/runs/{run_id}` 讀取同一筆 `PipelineRun`。

### CLI 路徑

CLI 直接在同一個 async process 中呼叫 orchestrator，輸出 JSON summary。它不寫 `pipeline_runs`，也不使用 DB progress reporter；這保留了手動重跑與 scheduler 以外的簡單執行路徑。

### `PipelineRun` 狀態

`queued → running → succeeded | failed`；`cancelled` 目前只保留資料模型值，沒有 cancel API。資料階段（ingest/decrypt/parse）有錯誤或 classify 整批 rollback 時為 failed；notify 是盡力而為通道，單筆 Telegram 失敗不會把已完整持久化的資料 run 標成 failed。

## 4. Parser 與來源擴充點

Parser 對外只需要 `BankParser.can_parse()` 與 `BankParser.parse()`，回傳與 ORM 無關的 `ParseResult`。`parser/banks/__init__.py` 會自動探索符合 `{bank}_v{N}.py` 的模組並註冊至 registry，目前有 7 個 v1 parser：CTBC、E.SUN、Taishin、UBOT、Cathay、SinoPac、Fubon。

解析流程會先依 `bank_configs.active_parser_version` 排候選，再以 `can_parse()` 判斷格式，成功後才建立資料庫資料。每筆 PDF 的同步解析工作放入 thread，並受 `PDF_PARSE_TIMEOUT_SECONDS` 保護；逾時會標成 `parse_failed`，worker 可繼續下一筆。

Ingestor 同時支援兩種帳單來源：一般 Gmail MIME PDF attachment，以及從 Gmail HTML 內連結觸發的 web-fetch。web-fetch 目前實作 FUBON，透過 fetcher registry、銀行登入憑證、captcha OCR／可選 LLM fallback 取得 PDF；來源記錄在 `staged_attachments.source_type`。

## 5. Domain data 與持久化

SQLite 使用 SQLAlchemy async session、WAL、`synchronous=NORMAL`、每連線 `busy_timeout=30000` 與 foreign keys。`updated_at` 由 SQLite trigger 補足 Core-style bulk UPDATE 不會觸發 ORM `onupdate` 的情況。

```text
Bill 1──* Transaction
Bill 1──* PaymentReminder      （發送去重／歷史）
Bill 1──1 ReminderSetting      （提醒策略覆寫）
Budget 1──* BudgetAlert
Category 1──* classification_rules
PipelineRun                  （獨立執行歷史，不與 Bill 建 FK）
```

重要持久化集合：

- `bills` / `transactions`：解析後的帳單與交易；金額以 NTD 整數元保存。
- `categories`：seed 與 user keyword 分類資料；`classification_rules` 是支援 keyword/exact/regex/priority 的進階使用者規則。
- `bank_configs` / `bank_settings`：前者是 parser／Gmail 設定，後者是使用者啟用與顯示偏好，兩者並存。
- `staged_attachments`：來源文件、相對 staging path、處理狀態與錯誤原因；Gmail 的穩定去重鍵是 `(gmail_message_id, gmail_part_id)`。
- `bank_secrets` / `bank_login_credentials`：以 `master.key` 加密的 PDF 密碼與銀行登入憑證；缺少 DB row 時才走 env fallback。
- `gmail_oauth_state`：短期 PKCE state；`pipeline_runs`：執行狀態、stage progress、參數與摘要。

完整欄位、索引與 migration chain 見 [`data.md`](data.md)。

## 6. API、前端與安全邊界

### API

`create_app()` 建立 FastAPI，公開 liveness/readiness health 端點與 auth session 端點；業務、pipeline、setup 路由統一套用 `verify_token`。認證接受有效 Bearer token 或 HMAC 簽章 session cookie。

完整 endpoint 清單見 [`backend.md`](backend.md)。API 錯誤統一為 `{success, message, data}`；OpenAPI `/docs`、`/redoc`、`/openapi.json` 預設關閉，需 `ENABLE_API_DOCS=true` 才開啟。

### Frontend

`App` 建立 QueryClient 與 BrowserRouter；除 `/login` 外的頁面經 `AuthGuard` 驗證 session，再進入 `Layout` 與 lazy-loaded route。Gmail OAuth 先回到前端 `/setup/gmail/callback`，再由該中介頁帶著 code/state 導向受保護的 backend callback，避免 token 出現在前端程式碼中。

Server state 使用 TanStack Query；交易、設定與 pipeline progress 的 cache invalidation／polling 都在 page 或 hook 中處理。完整頁面與 component map 見 [`frontend.md`](frontend.md)。

### Secrets 與設定

`Settings` 從 `.env`／環境變數載入；`.env.example` 是變數說明的 SSOT。API token、master key、Gmail credentials/token 與 bank secrets 都有獨立的檔案或加密儲存規則；文件只描述路徑與來源，不記錄實際秘密值。

Agent surfaces 共用 `ccas.services` 的安全投影；REST 提供 `/api/bills/payment-due` 與 `/api/pipeline/status`，CLI/MCP 僅允許唯讀查詢。`AGENT_WRITE_ENABLED` 預設為 false，且目前不會暴露任何寫入工具。

MCP client 的人工安裝與委託 AI 安裝步驟集中於 [`docs/mcp-installation.md`](../mcp-installation.md)；本文件只保留 as-built 契約，避免複製易漂移的 client 設定片段。

## 7. 測試與文件維護入口

```bash
./scripts/dev-test.sh                 # backend pytest
./scripts/dev-test.sh tests/unit/ --cov --cov-report=term-missing
./scripts/dev-lint.sh                 # ruff + format check + pyright
cd frontend && pnpm lint && pnpm build && pnpm test
cd frontend && pnpm e2e              # 需要可運作的應用環境
```

Backend unit coverage gate 目前由 `backend/pyproject.toml`、CI 與 pre-push 一致設定為 80%；integration 與 E2E 是獨立驗證層。

文件維護規則：

| 改動區域 | 先更新的文件 |
|---|---|
| pipeline、stage、progress、retry | 本文件、`CODEMAPS/backend.md`、`docs/RUNBOOK.md`（若操作方式改變） |
| ORM、migration、狀態值、索引 | `CODEMAPS/data.md`、本文件 |
| API route / schema | `CODEMAPS/backend.md`、本文件；必要時同步 frontend types |
| route、page、query cache | `CODEMAPS/frontend.md`、本文件 |
| env、compose、secret、服務入口 | `CODEMAPS/dependencies.md`、deployment / developer guide |
| 領域詞彙 | `CONTEXT.md`；不可逆且具取捨的決策才新增 ADR |
