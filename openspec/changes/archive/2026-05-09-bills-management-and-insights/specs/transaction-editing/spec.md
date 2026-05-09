## ADDED Requirements

### Requirement: Transaction 表新增使用者編輯欄位

系統 SHALL 在 `transactions` 表新增五個使用者編輯欄位：`manual_category_override` (bool, default false)、`note` (text, default '')、`tags` (JSON array, default '[]')、`merchant_alias` (str, default '')、`updated_at` (datetime nullable)。alembic migration SHALL 為加欄位、預設值填入既有 row，無破壞性變更。

#### Scenario: alembic migration 對既有資料無感

- **WHEN** 執行 `alembic upgrade head` 對既有 transactions 表（含歷史資料）
- **THEN** 系統 SHALL 為所有既有 row 填入欄位預設值（`manual_category_override = false`、`note = ''`、`tags = '[]'`、`merchant_alias = ''`、`updated_at = NULL`），既有交易展示 SHALL 不受影響

#### Scenario: 索引 (category_id, transaction_date) 加入

- **WHEN** migration 完成
- **THEN** 系統 SHALL 新增複合索引 `(category_id, transaction_date)` 補強 insights 查詢；既有 `(transaction_date)` 索引保留

### Requirement: PUT /api/transactions/{id} 編輯端點

系統 SHALL 提供 `PUT /api/transactions/{id}` 端點，body 為 partial update：`{category_id?, note?, tags?, merchant_alias?}`。後端 SHALL 對提供欄位執行 UPDATE、設 `updated_at = now()`、若 body 含 `category_id` SHALL 同步設 `manual_category_override = true`（即使值與既有相同）。

#### Scenario: 改 category 觸發 manual_category_override

- **WHEN** 使用者送 `PUT /api/transactions/123` body `{category_id: 5}`
- **THEN** 系統 SHALL 更新 `category_id = 5`、`manual_category_override = true`、`updated_at = now()`、回 200

#### Scenario: 僅改 note 不觸發 override

- **WHEN** 使用者送 body `{note: "晚餐請客"}`（無 category_id）
- **THEN** 系統 SHALL 僅更新 note、updated_at；`manual_category_override` 保持原值（如 false 仍為 false）

#### Scenario: tags 為 array

- **WHEN** body `{tags: ["公司", "商務午餐"]}`
- **THEN** 系統 SHALL 將 array 序列化為 JSON 寫入 `tags` 欄位、後續 GET 時還原為 array

#### Scenario: 不存在的 transaction id 回 404

- **WHEN** 送 `PUT /api/transactions/99999`、id 不存在
- **THEN** 系統 SHALL 回 404 並錯誤訊息「transaction not found」

#### Scenario: 422 validation 錯誤

- **WHEN** body `{category_id: 99999}` category 不存在
- **THEN** 系統 SHALL 回 422、錯誤訊息明示 category_id 無效

### Requirement: POST /api/transactions/{id}/note 快捷端點

系統 SHALL 提供 `POST /api/transactions/{id}/note` 端點 body `{note: str}`，僅更新 note 欄位、`updated_at`，方便前端 textarea debounce auto-save 直接呼叫不需構造完整 PUT body。

#### Scenario: 簡化 auto-save 流程

- **WHEN** 前端 note textarea debounce 後送 `POST /api/transactions/123/note` body `{note: "新備註"}`
- **THEN** 系統 SHALL 更新 note + updated_at、回 200；前端 SHALL 不需要附 category_id / tags / merchant_alias

### Requirement: DELETE /api/transactions/{id}/manual-override 重置覆寫

系統 SHALL 提供 `DELETE /api/transactions/{id}/manual-override` 端點，將 `manual_category_override = false` 並重新跑該 transaction 的分類流程（user_rules → engine → 預設）、寫入新 category_id、`updated_at = now()`。

#### Scenario: 重置後立即重新分類

- **WHEN** transaction 既有 `manual_category_override = true、category_id = 5`、使用者點「重置覆寫」
- **THEN** 系統 SHALL 設 `manual_category_override = false`、執行 user_rules + engine 分類、寫入新 category_id（可能仍為 5 或變化）、回 200 含新 category_id

#### Scenario: 重置不影響 note / tags / merchant_alias

- **WHEN** 重置 manual override
- **THEN** note、tags、merchant_alias 欄位 SHALL 不被清除，使用者個人 metadata 保留

### Requirement: classify 階段尊重 manual_category_override

Pipeline classify 階段針對每筆 transaction SHALL 檢查 `manual_category_override`：若為 true SHALL 跳過所有分類邏輯（user_rules、engine、預設），保留既有 `category_id`，不更新。stage_summary 內 SHALL 紀錄 `skipped_due_to_manual_override` 計數。

#### Scenario: 重跑 pipeline 不覆寫使用者編輯

- **WHEN** 使用者於 t1 改 category 為 X、t2 重新跑 pipeline
- **THEN** classify 階段 SHALL 看到該 transaction `manual_category_override = true` 而跳過、`category_id` 仍為 X、`updated_at` 不變

#### Scenario: stage_summary 內可見計數

- **WHEN** 一次 pipeline run 中有 5 筆 manual override
- **THEN** classify stage 在 `pipeline_runs.stage_summary` 內 SHALL 含 `skipped_due_to_manual_override: 5` 欄位、UI 揭示讓使用者驗證機制

### Requirement: 交易詳情頁含分類來源徽章

系統 SHALL 提供 `frontend/src/pages/transactions/[id].tsx` 詳情頁，含「分類來源」徽章，依優先序顯示：(a) `manual_override`（紫）、(b) `user_rule#<id>`（藍）、(c) `engine`（綠）、(d) `default`（灰）。徽章 hover SHALL 顯示 tooltip 解釋來源。

#### Scenario: 各層來源徽章正確

- **WHEN** transaction.manual_category_override = true
- **THEN** 徽章 SHALL 顯示「使用者覆寫」紫色

- **WHEN** classify 階段命中 user_rule id=3
- **THEN** 徽章 SHALL 顯示「個人規則 #3」藍色 + tooltip 含 pattern 內容（前 30 字元）

- **WHEN** 走既有 engine 內建規則命中
- **THEN** 徽章 SHALL 顯示「系統規則」綠色

- **WHEN** 全不命中
- **THEN** 徽章 SHALL 顯示「未分類（預設）」灰色

### Requirement: 交易列表頁含 inline category 快速改

`frontend/src/pages/transactions.tsx` 列表頁 SHALL 在每 row 提供 inline category select 快速改類別，改後立即 PUT、樂觀更新；若 PUT 失敗 SHALL revert 並 toast 錯誤。

#### Scenario: 列表 inline 改 category

- **WHEN** 使用者於列表 row 直接改 category
- **THEN** UI SHALL 立即顯示新 category、同時 send PUT、API 失敗時 revert + toast

#### Scenario: 列表 row 含「編輯」按鈕跳到詳情頁

- **WHEN** 使用者點某 row 的「編輯」按鈕
- **THEN** 系統 SHALL 跳到 `/transactions/{id}` 詳情頁，可編輯 note / tags / merchant_alias 等較多欄位
