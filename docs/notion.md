# 信用卡帳單自動化管理系統 (CCAS) 規格文件

> **Credit Card Automation System v1.0** | 建立日期：2026-03-26 | 更新日期：2026-03-27

---

## 1. 專案概述

本專案旨在解決多張信用卡（5+ 家銀行）導致的「帳單分散」、「格式不一」、「容易漏繳」等問題。透過 Gmail API 自動抓取帳單 PDF 附件，利用版本化的 Rule-based Parser（責任鏈模式）提取消費明細與繳款資訊，以關鍵字規則自動分類消費，並提供 Telegram Bot 即時通知（優先）及 React Dashboard 進行消費分析。

### 1.1 核心目標

- 自動化：每日排程自動抓取、解析、儲存帳單
- 可追蹤：所有消費明細結構化儲存，支援歷史查詢
- 即時通知：Telegram Bot 提供繳費提醒和消費摘要
- 分析洞察：Dashboard 提供消費趨勢、類別分布、銀行比較

---

## 2. 技術棧

| 層級 | 技術 |
|------|------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, APScheduler |
| PDF 解析 | pdfplumber + pikepdf (解密) + tabula-py (表格) |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui + Recharts |
| Bot | python-telegram-bot |
| Gmail | google-api-python-client (Gmail API) |
| Database | SQLite |
| Package Manager | uv (Python), pnpm (Frontend) |
| Testing | pytest (Backend), vitest (Frontend) |
| Deploy | Docker + Docker Compose |

---

## 3. 系統架構與流程

### 3.1 模組組成

1. **Ingestor (抓取層)**：對接 Gmail API，根據銀行設定過濾帳單郵件並下載 PDF 附件。
2. **Parser Engine (解析層)**：採用**責任鏈模式 (Chain of Responsibility)**，每家銀行獨立 parser 目錄，支援版本化（v1, v2...），新版格式不影響舊版。
3. **Classifier (分類層)**：基於關鍵字規則的消費自動分類引擎，使用可維護的商家-類別映射表。
4. **Storage (儲存層)**：使用 SQLite + SQLAlchemy ORM 儲存結構化帳單與消費明細。
5. **Interface (交互層)**：
    - **Telegram Bot**（優先）：即時提醒、消費查詢、繳費狀態標記。
    - **React Dashboard**：消費趨勢分析、明細篩選、帳單管理。
6. **API (服務層)**：FastAPI 提供 RESTful API，前後端分離。
7. **Scheduler (排程層)**：APScheduler 管理每日自動抓取與通知任務。

### 3.2 運作流程

1. 每日排程啟動（APScheduler 觸發 `run_pipeline()`）
2. **Ingest**: 登入 Gmail 搜尋新帳單（根據 bank_configs 中的 gmail_filter），下載 PDF 附件到 staging 區
3. **Decrypt**: 讀取 `bank_configs.pdf_password_rule` 解密加密 PDF（pikepdf），未加密 PDF 直接透通
4. **Parse**: 依序調用該銀行的 Parser（從 active_parser_version 開始，再 fallback 由新到舊）
5. 所有版本失敗 → 標記為 `parse_failed`，進入人工審查佇列
6. **Classify**: 解析成功 → 關鍵字分類消費明細（規則來自 categories 資料表）
7. 存入資料庫（Bill + Transaction 原子寫入）
8. **Notify**: 發送 Telegram 通知（新帳單、解析失敗）
9. 各階段獨立容錯，單筆失敗不中止整批

---

## 4. 資料庫設計 (Schema)

### 4.1 `bills` (帳單主表)

| 欄位名稱 | 型態 | 說明 |
|:---------|:-----|:-----|
| `id` | INTEGER | Primary Key, 自動遞增 |
| `bank_code` | TEXT | 銀行代碼 (如: `CTBC`, `CATHAY`, `ESUN`) |
| `billing_month` | TEXT | 帳單月份 (格式: `YYYY-MM`) |
| `total_amount` | INTEGER | 應繳總金額 |
| `due_date` | DATE | 繳款截止日 |
| `is_paid` | BOOLEAN | 0: 未繳, 1: 已繳 (預設 0) |
| `file_path` | TEXT | PDF 原始檔案路徑 |
| `created_at` | DATETIME | 資料匯入時間 |

### 4.2 `transactions` (消費明細表)

| 欄位名稱 | 型態 | 說明 |
|:---------|:-----|:-----|
| `id` | INTEGER | Primary Key, 自動遞增 |
| `bill_id` | INTEGER | Foreign Key (關聯 `bills.id`) |
| `trans_date` | DATE | 消費日期 |
| `posting_date` | DATE | 入帳日期 (nullable，部分銀行區分消費日與入帳日) |
| `merchant` | TEXT | 商家名稱 |
| `amount` | INTEGER | 台幣金額 |
| `currency` | TEXT | 原始幣別 (TWD/USD/JPY...) |
| `original_amount` | INTEGER | 原始幣別金額 (TWD 時為 null) |
| `card_last4` | TEXT | 卡號後四碼 |
| `installment_current` | INTEGER | 目前期數 (非分期時為 null) |
| `installment_total` | INTEGER | 總期數 (非分期時為 null) |
| `category` | TEXT | 自動分類結果 |
| `note` | TEXT | 備註 |
| `created_at` | DATETIME | 建立時間 |

### 4.3 `categories` (商家分類映射表)

| 欄位名稱 | 型態 | 說明 |
|:---------|:-----|:-----|
| `id` | INTEGER | Primary Key, 自動遞增 |
| `keyword` | TEXT | 商家關鍵字 (如: "全聯", "7-ELEVEN") |
| `category` | TEXT | 消費類別 (如: "日用品", "餐飲") |

### 4.4 `bank_configs` (銀行設定表)

| 欄位名稱 | 型態 | 說明 |
|:---------|:-----|:-----|
| `id` | INTEGER | Primary Key, 自動遞增 |
| `bank_code` | TEXT | 銀行代碼 (UNIQUE) |
| `bank_name` | TEXT | 銀行名稱 |
| `gmail_filter` | TEXT | Gmail 搜尋關鍵字 (如: "from:service@ctbcbank.com subject:帳單") |
| `pdf_password_rule` | TEXT | 密碼規則描述 (如: "身分證後四碼", "生日 MMDD") |
| `active_parser_version` | TEXT | 目前使用的 parser 版本 (如: "v2") |
| `is_active` | BOOLEAN | 是否啟用 (預設 true，停用後 ingestor 與 parser 不處理此銀行) |

---

## 5. Parser 版本化設計

### 5.1 目錄結構

```
parser/
  base.py              # AbstractParser 抽象基類
  registry.py          # ParserRegistry 版本鏈解析
  result.py            # ParseResult 資料類別
  banks/
    ctbc/
      __init__.py
      v1.py            # CTBC 2024 格式
      v2.py            # CTBC 2026 新格式
    cathay/
      __init__.py
      v1.py
    esun/
      __init__.py
      v1.py
```

### 5.2 解析流程

1. `ParserRegistry` 根據 `bank_code` 找到該銀行所有 parser 版本
2. 從最新版本開始嘗試：`v2.can_parse(pdf)` → 若 False → `v1.can_parse(pdf)`
3. 找到能解析的版本 → 執行 `parse(pdf)` → 返回 `ParseResult`
4. 全部版本失敗 → 標記 `parse_failed`，進入人工審查佇列

### 5.3 新增/更新 Parser

當銀行改變 PDF 格式時：
1. 在該銀行目錄下新增 `v{n+1}.py`
2. 實作 `can_parse()` 與 `parse()` 方法
3. Registry 自動偵測新版本，下次解析時優先使用

---

## 6. Telegram Bot 指令

| 指令 | 功能 |
|------|------|
| `/status [all\|unpaid\|paid]` | 查看本月帳單繳費狀態（預設 all，可篩選未繳/已繳） |
| `/upcoming` | 查看 7 天內即將到期的帳單 |
| `/paid {bill_id}` | 標記帳單已繳 |
| `/summary {YYYY-MM}` | 查看指定月份消費摘要 |
| `/category {YYYY-MM}` | 依類別查看消費分布 |

### 6.1 主動通知

- 帳單到期前 3 天、1 天自動提醒
- 新帳單解析完成時通知
- 解析失敗時通知（需人工處理）

---

## 7. Dashboard 頁面

| 頁面 | 功能 |
|------|------|
| Overview | 本月消費總覽、繳費狀態卡片、即將到期帳單 |
| Transactions | 可搜尋/篩選的消費明細表、CSV 匯出 |
| Analytics | 月趨勢圖 (line)、類別分布 (pie)、銀行比較 (bar) |
| Bills | 帳單列表、繳費狀態切換、PDF 檔案連結 |
| Settings | 銀行設定管理、分類關鍵字管理 |

---

## 8. 專案結構

```
ccas/
  backend/
    src/ccas/
      ingestor/              # Gmail API 整合
        gmail_client.py      # OAuth + 郵件抓取
        filter.py            # 帳單郵件過濾
        downloader.py        # PDF 下載 + 解密
      parser/
        base.py              # AbstractParser
        registry.py          # ParserRegistry
        result.py            # ParseResult
        banks/               # 各銀行 parser
      storage/
        models.py            # SQLAlchemy models
        repository.py        # Repository pattern
        database.py          # Engine + session
      decryptor/
        service.py           # PDF 解密服務 (pikepdf)
      classifier/
        engine.py            # 關鍵字分類引擎 (規則來源為 categories 資料表)
      pipeline/
        orchestrator.py      # Pipeline 串接 (ingest->decrypt->parse->classify->notify)
      bot/
        handlers.py          # Bot 指令處理
        notifications.py     # 主動通知
      api/
        routes/              # FastAPI routes
        schemas.py           # Pydantic schemas
        app.py               # App factory
      scheduler/
        jobs.py              # 排程任務
      core/
        exceptions.py        # 共用例外階層 (CcasError)
        logging.py           # 結構化日誌 (JSON formatter, secret redaction)
      config.py              # 設定管理
    tests/
      unit/                  # 純單元測試
      integration/           # 整合測試
      e2e/                   # 端到端 pipeline 測試
    pyproject.toml
    Dockerfile
  frontend/
    src/
      pages/                 # 頁面元件
      components/            # 共用元件
      api/                   # API client
      types/                 # TypeScript 型別
    Dockerfile
  docker-compose.yaml
  openspec/                  # OpenSpec 工作流
  docs/                      # 文件
```

---

## 9. 開發方法

- **TDD (Test-Driven Development)**：所有功能先寫測試再實作
- **OpenSpec 驅動**：每個開發階段對應一個 OpenSpec change
- **Docker 化**：開發與部署環境一致

### 9.1 開發階段

1. Foundation Setup -- 專案初始化、DB models、Docker、Seed Data
2. Backend API -- FastAPI RESTful API（含 Bearer Token 認證）
3. Gmail Ingestor -- Gmail 整合、OAuth token 刷新、retry 策略
4. PDF Decryptor -- PDF 解密（pikepdf）、密碼規則、staging 狀態管理
5. Parser Engine -- 解析引擎核心、版本化機制、due_date 提取
6. Keyword Classifier -- 消費分類引擎（規則來自 categories 資料表）
7. Telegram Bot -- Bot 指令與通知、retry 策略
8. Frontend Dashboard -- React Dashboard（5 頁面）
9. Pipeline Scheduler -- Pipeline 串接（5 階段）、APScheduler、繳費提醒排程
10. Integration & Polish -- 端對端測試、例外階層、結構化日誌、錯誤處理
