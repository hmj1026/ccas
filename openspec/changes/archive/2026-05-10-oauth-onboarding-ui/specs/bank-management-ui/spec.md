## ADDED Requirements

### Requirement: bank_settings 為運行期啟用狀態 SSOT

系統 SHALL 新增 `bank_settings` 資料表（`code` PK、`enabled` bool、`display_name` str、`notes` text、`created_at`、`updated_at`），作為 bank 啟用 / 停用狀態的單一真實來源。`banks.yaml` SHALL 退回為靜態元資料（parser 對應、欄位 schema、是否 require password），`enabled` 欄位若仍存在 SHALL 僅為 fallback。

#### Scenario: 首次啟動由 entrypoint seed bank_settings

- **WHEN** 全新部署、`bank_settings` 表為空、`banks.yaml` 含 7 個銀行
- **THEN** entrypoint SHALL 在 alembic migration 後對每個 yaml bank 執行 INSERT OR IGNORE：`enabled` = `yaml.enabled` 或 true、`display_name` = `yaml.display_name`、`notes` = null

#### Scenario: 既有 bank_settings 不被 seed 覆寫

- **WHEN** 升級啟動、`bank_settings.code='ctbc'` 已存在 `enabled=false`
- **THEN** entrypoint seed SHALL 不覆寫該 row，使用者既有設定保留

#### Scenario: yaml 中已移除的銀行 DB row 不自動刪除

- **WHEN** 開發者從 `banks.yaml` 移除某銀行條目（如停止支援）、bank_settings 仍有對應 row
- **THEN** entrypoint SHALL 不自動刪除該 DB row、`/setup/banks` UI SHALL 將其標記為「孤兒（yaml metadata 缺失）」並提供「移除 DB row」按鈕

### Requirement: bank enabled 解析優先序

Pipeline 各階段（ingest、decrypt、parse、classify、notify）查詢 bank 是否 enabled 時 SHALL 依序：(1) `bank_settings.enabled`（DB row 存在）→ (2) `banks.yaml` 中對應條目的 `enabled` 欄位 → (3) 預設 true。

#### Scenario: DB 設 false 時 ingest 跳過

- **WHEN** `bank_settings.code='esun'.enabled=false` 且 yaml `esun.enabled=true`
- **THEN** ingest 階段 SHALL 跳過 esun 對應 Gmail 標籤的所有 attachments、log 記錄 `[INFO] esun disabled in bank_settings, skipping ingest`

#### Scenario: DB 無 row 但 yaml 設 false 仍跳過

- **WHEN** `bank_settings` 無 esun row、yaml `esun.enabled=false`
- **THEN** ingest 階段 SHALL fallback 到 yaml.enabled、跳過 esun

#### Scenario: 兩處皆無設定預設 enabled

- **WHEN** 新加入的銀行 yaml 無 `enabled` 欄位、DB 也無 row
- **THEN** 系統 SHALL 預設 enabled，ingest 正常處理

### Requirement: GET /api/setup/banks 列出 + 狀態指標

系統 SHALL 提供 `GET /api/setup/banks` 端點，JOIN `banks.yaml` 元資料 + `bank_settings` DB row + 既有 ingest / parse / staging 統計，回傳每銀行的當前狀態與可見性指標。Response 結構 SHALL 包含至少：`code`、`display_name`、`enabled`、`metadata_missing`、`last_ingest_at`、`total_attachments`、`failed_decryption_count`、`requires_password`。

#### Scenario: 列表含完整指標

- **WHEN** 前端呼叫 `GET /api/setup/banks`
- **THEN** response SHALL 為陣列、每項含上述所有欄位、`last_ingest_at` 與 `total_attachments` 從 `staged_attachments` 與既有 ingest 紀錄計算

#### Scenario: 孤兒銀行被標記

- **WHEN** `bank_settings` 含 yaml 已移除的 bank code
- **THEN** 該項 `metadata_missing` SHALL 為 true、其他元資料欄位（如 `display_name`）SHALL 從 DB row 取（DB 仍有 `display_name`）

### Requirement: PUT /api/setup/banks/{code} 更新啟用狀態

系統 SHALL 提供 `PUT /api/setup/banks/{code}` 端點，body `{enabled?: bool, display_name?: str, notes?: str}`，UPDATE `bank_settings` 對應 row。不存在 code 的請求 SHALL 回 404。Pipeline 階段 SHALL 在下次執行時讀取最新狀態（不需要重啟 backend / worker）。

#### Scenario: 停用某銀行

- **WHEN** 前端送 `PUT /api/setup/banks/ctbc` body `{enabled: false}`
- **THEN** 系統 SHALL 更新 `bank_settings.code='ctbc'.enabled=false`、回 200、後續 pipeline ingest SHALL 跳過 ctbc

#### Scenario: 不存在的 bank code 回 404

- **WHEN** 前端送 `PUT /api/setup/banks/unknown_bank`
- **THEN** 系統 SHALL 回 404，不建立新 row（避免使用者誤建立）

#### Scenario: 變更立即生效（無快取問題）

- **WHEN** 使用者於 `/setup/banks` toggle disable ctbc → 立即點「立刻執行 pipeline」
- **THEN** 該次 pipeline run SHALL 跳過 ctbc，無需重啟 worker；驗證方式為 `GET /api/pipeline/runs/{id}` stage_summary 內 ctbc 不出現於 ingest 階段

### Requirement: /setup/banks 前端頁面

系統 SHALL 提供 `frontend/src/pages/setup/banks.tsx`，路由 `/setup/banks`。頁面 SHALL 為表格，欄位 `code / display_name / enabled toggle / 已收 PDF 數 / 最後 ingest 時間 / 操作按鈕`。toggle 變更 SHALL 立即送 PUT、樂觀更新 UI、API 失敗時 revert。

#### Scenario: toggle 變更樂觀更新

- **WHEN** 使用者點某銀行 toggle 從 enabled 變 disabled
- **THEN** UI SHALL 立即顯示為 disabled、同時 send PUT；若 PUT 失敗 SHALL revert 並 toast 錯誤訊息

#### Scenario: 孤兒銀行有「移除 DB row」按鈕

- **WHEN** 表格內某 row `metadata_missing: true`
- **THEN** 該 row SHALL 顯示橘色「孤兒」badge 與「移除 DB row」按鈕；按鈕點擊後彈 confirm dialog → DELETE `bank_settings` row

#### Scenario: 列表頂部摘要

- **WHEN** 頁面載入完成
- **THEN** 表格頂部 SHALL 顯示「N 銀行已啟用 / M 已停用 / K 孤兒」摘要文字
