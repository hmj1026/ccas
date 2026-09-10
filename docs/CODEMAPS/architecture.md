<!-- Verified: 2026-09-10 | Canonical as-built reference: current-implementation.md -->

# Architecture

本文件是架構入口與導覽；完整的目前實作基線請看
[current-implementation.md](./current-implementation.md)。

## System Overview

CCAS 將信用卡帳單從 Gmail 或銀行網銀 web-fetch 匯入，依序解密、解析、分類，
再提供 REST API、React 管理介面與 Telegram 通知。Redis/RQ 負責非同步 pipeline，
APScheduler 負責排程，SQLite 負責持久化。

## Runtime Topology

```
                    ┌──────────────┐
                    │ React / nginx│
                    └──────┬───────┘
                           │ /api
                    ┌──────▼───────┐
                    │ FastAPI      │─── SQLite (WAL)
                    └──────┬───────┘
                           │ RQ job
                    ┌──────▼───────┐       ┌──────────────┐
Gmail / web-fetch ─>│ Redis / RQ   │<──────│ APScheduler  │
                    └──────┬───────┘       └──────────────┘
                           │
                    ┌──────▼───────┐       ┌──────────────┐
                    │ Worker       │──────>│ Telegram bot │
                    └──────────────┘       └──────────────┘
```

## Pipeline

```
Ingest → Decrypt → Parse → Classify → Notify
```

每個 stage 都以資料庫中的 `StagedAttachment` 或帳單／交易資料作為邊界，
由 `PipelineRun` 記錄整體狀態、目前 stage 與每個 stage 的摘要。任一 stage
的單筆錯誤會被記錄並隔離；stage 完成後 pipeline 仍可依 orchestrator 的流程
繼續處理後續 stage。

## Module Map

```
backend/src/ccas/
├── api/        FastAPI app、auth、業務與 setup routers
├── ingestor/   Gmail client、附件 staging、銀行 web-fetch
├── decryptor/  PDF 密碼解析與解密
├── parser/     銀行 parser registry、PDF/OCR intake
├── classifier/ 使用者規則與內建關鍵字分類
├── bot/        Telegram commands、帳單與預算通知
├── pipeline/   orchestrator、RQ jobs、progress reporter
├── scheduler/  APScheduler jobs 與 heartbeat
├── storage/    SQLAlchemy models、queries、secrets
└── tools/      銀行設定、Gmail auth 與維運工具

frontend/src/
├── pages/      dashboard、交易、帳單、insights、operations、settings、setup
├── components/ 共用版面、狀態、預算、匯出與圖表元件
└── lib/        API client、React Query hooks 與 TypeScript types
```

## Cross-cutting Contracts

- API 的業務與 setup 路由使用 Bearer token 或 session cookie；health endpoints
  與 `GET/POST /api/auth/session` 是公開入口，登出則仍需有效認證。
- 檔案路徑以 `STAGING_DIR` 為根；資料庫只保存相對 `staged_path`。
- pipeline 的輸入可由 CLI、API/RQ 或 scheduler 觸發；三者共用相同 stage
  orchestrator。
- parser 透過 registry 與 bank/version 命名慣例發現實作；新增銀行時需同時補
  parser、設定與測試。

## Detail Maps

- [Backend](./backend.md)：API、pipeline stage、設定與後端模組邊界
- [Frontend](./frontend.md)：路由、元件、狀態與 API client
- [Data](./data.md)：資料表、關係與 migration chain
- [Dependencies](./dependencies.md)：外部服務、Compose 與 runtime 依賴
