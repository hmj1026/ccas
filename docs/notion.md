# 信用卡帳單自動化管理系統 (CCAS) 專案方向

> **Credit Card Automation System v1.1** | 建立日期：2026-03-26 | 更新日期：2026-09-15

---

## 1. 這份文件的定位

本文件用來說明 CCAS 的產品願景、目前落地狀態與下一步方向；它不是逐項 endpoint
或部署參數的操作手冊。

它**不是**系統行為的最終權威來源。

- `docs/CODEMAPS/current-implementation.md`：runtime as-built 行為的入口
- `openspec/specs/`：需求意圖與已接受設計，可能保留歷史命名
- `CLAUDE.md`：開發流程、指令與 repo 工作方式的 SSOT
- `docs/notion.md`：產品方向、階段目標、現況摘要

---

## 2. 產品願景

CCAS 的長期目標，是把分散在 Gmail、PDF、聊天提醒與人工記帳之間的信用卡帳單流程，整理成一條可以持續運行的自動化管線：

1. 自動從 Gmail 擷取帳單附件
2. 依銀行規則解密與解析 PDF
3. 將帳單與交易明細結構化儲存
4. 自動分類消費
5. 透過 Telegram 與 Dashboard 提供提醒、查詢與分析

### 2.1 長期目標

- 自動化：降低人工下載、整理、提醒的工作量
- 可追蹤：每筆帳單與交易都有可查詢的結構化資料
- 可營運：系統可在本機或遠端主機穩定部署與日常使用
- 可擴張：先從單一銀行做穩，再逐步擴展到多家銀行

---

## 3. 當前產品現況

目前專案已具備可自架 MVP 的完整主線，但各銀行 parser 的資料覆蓋率與 QA 成熟度不同：

- Gmail → ingest → decrypt → parse → classify → notify 的端到端 pipeline 已落地
- 7 家銀行均有 v1 parser；FUBON 另有 web-fetch 與 manual-staging fallback
- 已有 Telegram Bot、Dashboard、REST API、Agent CLI、stdio MCP 與 loopback HTTP MCP
- 已提供 Docker dev、self-build production 與 pull-only production 路徑

### 3.1 目前已落地能力

- Gmail API 抓取 PDF 附件
- PDF 解密與 staging 流程
- 7 家銀行 parser 與 OCR 商戶辨識
- 消費分類與 seed data
- Telegram 通知與帳單互動
- React Dashboard、Insights、設定中心與 Gmail OAuth onboarding
- FastAPI REST API
- RQ + Redis 背景工作模型
- SQLite + Alembic schema 管理
- Docker 本機、self-build production 與 pull-only production 部署

### 3.2 目前尚未達成的能力

- 已有 7 家銀行 parser 初版（CTBC／CATHAY／ESUN／TAISHIN／FUBON／SINOPAC／UBOT），但 OCR 覆蓋率、分類規則與 QA 資料集仍需補強
- 人工審查流程目前仍偏底層狀態與記錄，沒有完整操作介面
- Agent write tools 尚未開放，MCP 仍限定 loopback 與唯讀工具
- 完整人工審查工作流、跨環境 release sign-off 與各銀行長期 QA 資料集仍需補強

### 3.3 當前主線判斷

已有 7 家銀行 parser 初版實作，短期焦點不在新增銀行，而在：

**各銀行 parser 的生產穩定性、OCR 準確度、分類規則、QA 資料集與可觀測性；同時維持部署與唯讀 Agent 介面的安全邊界。**

---

## 4. 技術方向

| 層級 | 目前方向 |
|------|------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Alembic |
| Queue / Scheduler | RQ + Redis 為主，APScheduler 僅作獨立 scheduler 選項 |
| PDF 解析 | pdfplumber + pikepdf，必要時以 OCR 補足 |
| OCR | pytesseract + tesseract-ocr + chi_tra |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui + Recharts |
| Bot | python-telegram-bot |
| Gmail | google-api-python-client |
| Database | SQLite (WAL mode) |
| Package Manager | uv, pnpm |
| Testing | pytest, vitest |
| Deploy | Docker + Docker Compose |

### 4.1 技術說明

- `tabula-py` 目前仍在依賴清單中，但當前 parser 主線已偏向 `pdfplumber + OCR`，不再把 tabula 視為主要解析策略。
- 排程模型以 **RQ worker 與 Redis** 為主，避免在 FastAPI process 內直接承載排程與長任務。
- OCR 已從實驗性能力進入主線，特別是 CTBC 商戶名稱辨識。

---

## 5. 系統架構

### 5.1 模組組成

1. **Ingestor**：根據 `bank_config` 從 Gmail 搜尋並下載 PDF
2. **Decryptor**：依銀行密碼規則解密 PDF
3. **Parser Engine**：依銀行與版本選擇 parser，輸出 `ParseResult`
4. **Classifier**：用關鍵字規則對交易分類
5. **Storage**：SQLite + SQLAlchemy ORM
6. **API**：FastAPI 提供 Dashboard 與外部操作端點
7. **Bot**：Telegram 指令、通知與帳單狀態互動
8. **Worker / Scheduler**：RQ worker 執行背景工作；定期觸發可由外部 cron 或獨立 scheduler 負責
9. **Frontend Dashboard**：Overview、Transactions、Insights、Bills、Operations、Settings、Setup

### 5.2 當前標準流程

1. 由 API、CLI 或 scheduler 觸發 pipeline
2. **Ingest**：根據 `gmail_filter` 抓取附件到 staging
3. **Decrypt**：依 `pdf_password_rule` 解密
4. **Parse**：選擇對應 parser；CTBC 已支援 OCR 商戶辨識
5. **Classify**：依關鍵字分類
6. **Persist**：寫入 `Bill` 與 `Transaction`
7. **Notify**：查詢 `is_notified = False` 的帳單，發送 Telegram 後標記完成

### 5.3 容錯方向

- 各階段盡量獨立容錯，單筆失敗不拖垮整批
- parser 與 pipeline 失敗需保留足夠的結構化 log
- 需要人工介入的案件先以狀態與失敗資訊標記，後續再補更完整的 review workflow

---

## 6. 目前資料模型重點

### 6.1 `bills`

目前重點欄位包括：

- `bank_code`
- `billing_month`
- `total_amount`
- `due_date`
- `is_paid`
- `is_notified`
- `file_path`
- `created_at`

其中：

- `is_paid`：繳費狀態
- `is_notified`：Telegram 通知狀態，避免重複發送
- `parse_method` / `parse_confidence` / `needs_review` / `review_reasons`：解析結果觀測與人工複核提示

### 6.2 `transactions`

目前重點欄位包括：

- `trans_date`
- `posting_date`
- `merchant`
- `amount`
- `currency`
- `original_amount`
- `card_last4`
- `installment_current`
- `installment_total`
- `category`
- `note`

### 6.3 其他核心表

- `categories`：分類規則
- `bank_configs`：銀行啟用狀態、Gmail filter、PDF 密碼規則、active parser version

---

## 7. Parser 策略

### 7.1 目標策略

Parser 保持版本化設計，允許同一家銀行有多個 parser 版本共存，讓新舊 PDF 格式可以並行支援。

### 7.2 當前實況

- 目前有 7 個 v1 parser（CTBC／CATHAY／ESUN／TAISHIN／FUBON／SINOPAC／UBOT）
- OCR 主要用於需要影像補足的欄位；FUBON CAPTCHA 另有 ddddocr 與可選 LLM fallback
- parser 均已接入 registry；穩定性、OCR 覆蓋率與 QA 資料集仍按銀行逐步補強

### 7.3 實作原則

- 優先使用可穩定取得的文字資訊
- 必要時使用 OCR 補足圖片型欄位
- parser 失敗時保留足夠資訊，以利後續修正與人工處理

---

## 8. 使用者介面方向

### 8.1 Telegram Bot

Bot 仍是高優先級介面，因為它直接承接：

- 新帳單通知
- 繳費提醒
- 帳單狀態互動
- 摘要查詢

### 8.2 Dashboard

Dashboard 是第二條主要介面，負責：

- 消費總覽
- 明細查詢與篩選
- 分析圖表
- 帳單管理
- 設定管理

### 8.3 當前建議

不要再把 Bot 和 Dashboard 描述成二選一。較合理的產品定位是：

- **Bot**：即時提醒與快速操作
- **Dashboard**：查詢、分析與管理

---

## 9. 近期實作方向

### 9.1 Phase 1：單一主線與 parser 穩定化（已落地，持續維護）

目標是讓單一銀行流程可以穩定日常使用：

- CTBC parser 與 OCR 穩定
- pipeline / notify / classification 關鍵路徑可運行
- 必要 seed data 與預設 bank config 完整
- E2E 驗證可重複執行

### 9.2 Phase 2：部署與營運能力（已落地，持續維護）

目標是讓系統可以在遠端主機自架：

- production Docker Compose
- frontend nginx `/api` proxy
- credential mount 策略
- deployment guide
- dev / prod compose 邊界清楚

### 9.3 Phase 3：開發者體驗與維運工具（已落地，持續維護）

- 本機一鍵啟動與 env validation
- DB / Redis GUI 工具
- 更完整的排錯文件
- 更清楚的 seed / reset / health check 流程

### 9.4 Phase 4：多銀行品質與人工審查（進行中）

- 7 家 parser 的驗證資料集與回歸品質
- parser 驗證資料集
- 更完整的人工審查與例外處理流程

---

## 10. 專案結構摘要

```text
backend/src/ccas/
  api/                FastAPI routes
  bot/                Telegram bot 與通知
  classifier/         消費分類
  decryptor/          PDF 解密
  ingestor/           Gmail 抓取
  parser/             parser registry、各銀行 parser、OCR
  pipeline/           orchestrator、worker、summary、options
  scheduler/          獨立 scheduler 入口
  storage/            database、models、queries

frontend/src/
  pages/              lazy-loaded route pages（含 setup wizard）
  components/         layout 與共用 UI
  lib/                API client、types、utils

config/
  bank-code-registry.yaml
  banks.example.yaml

scripts/              18 個 shell scripts
  setup.sh
  start.sh
  check-env.sh
  docker-entrypoint.sh
```

---

## 11. 開發原則

- TDD 優先
- OpenSpec 驅動
- 先收斂單一主線，再擴張功能廣度
- 文件需區分「願景」與「已落地能力」
- Docker 開發與部署流程要盡量一致

---

## 12. 目前最需要避免的誤解

- 不是所有銀行都已經落地
- APScheduler 不是目前主排程模型
- tabula 不是目前 parser 主軸
- `notion.md` 不是功能真相的最終來源
- 專案短期目標不是「先做 5+ 家銀行」，而是「先把 CTBC 自架 MVP 做穩」
