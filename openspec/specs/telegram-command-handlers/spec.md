# telegram-command-handlers Specification

## Purpose
TBD - created by archiving change telegram-bot. Update Purpose after archive.
## Requirements
### Requirement: 僅回應白名單 chat_id
系統 SHALL 僅處理來自白名單 chat_id 的指令與訊息，非白名單來源靜默忽略。白名單 SHALL 從 `Settings.telegram_allowed_chat_ids` 欄位載入（透過 pydantic-settings 從 `.env` 或環境變數取得），而非直接讀取 `os.environ`。

`load_allowed_chat_ids()` SHALL 接受一個 `raw: str` 參數（逗號分隔的 chat_id 字串），解析後回傳 `frozenset[int]`。

#### Scenario: 白名單使用者正常使用指令
- **WHEN** 白名單中的使用者送出任何指令
- **THEN** bot 正常處理並回覆

#### Scenario: 非白名單使用者被靜默忽略
- **WHEN** 非白名單的 chat_id 送出任何訊息或指令
- **THEN** bot 不回覆任何內容，不記錄為錯誤

#### Scenario: 從 Settings 載入白名單
- **WHEN** `Settings.telegram_allowed_chat_ids` 為 `"111,222,333"`
- **THEN** `load_allowed_chat_ids("111,222,333")` 回傳 `frozenset({111, 222, 333})`

#### Scenario: 空白名單
- **WHEN** `Settings.telegram_allowed_chat_ids` 為空字串
- **THEN** `load_allowed_chat_ids("")` 回傳空 `frozenset()`

### Requirement: 支援 `/status [all|unpaid|paid]` 查詢本月帳單狀態
系統 SHALL 支援 `/status [all|unpaid|paid]` 指令，查詢本月帳單繳費狀態；若未提供 filter，預設為 `all`。回覆中每筆帳單附上 `bill_id`，帳單依銀行分組顯示。

#### Scenario: `/status` 未帶參數時回傳本月全部帳單（依銀行分組）
- **WHEN** 使用者送出 `/status`
- **THEN** bot 會回傳本月所有帳單，依銀行分組，每筆包含 bill_id、金額、到期日與已繳狀態

#### Scenario: `/status unpaid` 僅回傳未繳帳單
- **WHEN** 使用者送出 `/status unpaid`
- **THEN** bot 只會回傳本月尚未標記為已繳的帳單，依銀行分組，每筆附上 bill_id

### Requirement: 支援 `/upcoming` 查詢即將到期帳單
系統 SHALL 支援 `/upcoming` 指令，列出未來 7 天內到期且尚未繳款的帳單。

#### Scenario: 查詢 7 天內即將到期帳單
- **WHEN** 使用者送出 `/upcoming`
- **THEN** bot 會回傳所有在未來 7 天內到期且 `is_paid=false` 的帳單摘要

### Requirement: 支援月份摘要與類別分布查詢
系統 SHALL 支援 `/summary {YYYY-MM}` 與 `/category {YYYY-MM}`，分別回傳指定月份的消費摘要與類別分布。

#### Scenario: `/summary` 回傳指定月份摘要（依銀行分組）
- **WHEN** 使用者送出 `/summary 2026-03`
- **THEN** bot 會回傳該月份總消費、依銀行分組的消費小計與帳單狀態摘要

#### Scenario: `/category` 回傳指定月份分類分布
- **WHEN** 使用者送出 `/category 2026-03`
- **THEN** bot 會回傳該月份依分類彙總的消費金額摘要

