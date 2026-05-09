## ADDED Requirements

### Requirement: classification_rules 表結構

系統 SHALL 新增 `classification_rules` 資料表，作為使用者個人分類規則的 SSOT。欄位 SHALL 含：`id` (UUID PK)、`pattern` (text)、`pattern_type` (enum: keyword / exact / regex)、`category_id` (FK to categories)、`priority` (int, default 0)、`enabled` (bool, default true)、`created_at`、`updated_at`。索引 SHALL 含 `(priority DESC, enabled)` 與 `(category_id)`。

#### Scenario: 建表後可查詢

- **WHEN** alembic upgrade 完成、有 3 條 rules priority 分別為 100、50、10
- **THEN** `SELECT * FROM classification_rules WHERE enabled=true ORDER BY priority DESC` SHALL 命中索引、回傳順序為 100、50、10

#### Scenario: alembic downgrade 為 drop table

- **WHEN** `alembic downgrade -1`
- **THEN** 系統 SHALL drop `classification_rules` 表、不影響 `transactions` 既有資料

### Requirement: 三種 pattern_type 匹配語意

系統 SHALL 支援三種 pattern_type 匹配 `transaction.description` 欄位（既有，從 PDF parse 出的商家描述）：
- `keyword`：`description.lower()` 包含 `pattern.lower()` 子字串（最常見）
- `exact`：`description.lower()` 等於 `pattern.lower()`
- `regex`：`re.search(pattern, description, re.IGNORECASE)`

每條規則匹配 SHALL 加 100ms timeout（防止 catastrophic regex backtracking 拖累 pipeline）。

#### Scenario: keyword 包含匹配

- **WHEN** rule pattern = "STARBUCKS"、type = keyword、transaction.description = "STARBUCKS COFFEE TPE BR"
- **THEN** matcher SHALL 回 true

#### Scenario: exact 完全相等

- **WHEN** rule pattern = "STARBUCKS"、type = exact、transaction.description = "STARBUCKS COFFEE TPE BR"
- **THEN** matcher SHALL 回 false（包含但不相等）

#### Scenario: regex 套用 IGNORECASE

- **WHEN** rule pattern = `^uber\s+(eats|moto)`、type = regex、description = "UBER EATS TAIPEI"
- **THEN** matcher SHALL 回 true（不分大小寫）

#### Scenario: regex catastrophic backtracking 觸發 timeout

- **WHEN** rule pattern = `(a+)+$`、description = "aaaaaaaaaaaaaaaaaa!"（會 backtrack 爆炸）
- **THEN** matcher SHALL 在 100ms 內 timeout、log warning「規則 #N 匹配逾時，已跳過」、繼續處理下一規則；該 transaction 走後續規則或預設分類

### Requirement: classify 階段優先序

Pipeline classify 階段針對每筆 `manual_category_override = false` 的 transaction SHALL 依序：(1) query `classification_rules WHERE enabled = true ORDER BY priority DESC` → 對每條規則嘗試 match、命中第一條 SHALL 寫入 `category_id` 並停止匹配、(2) 若無 user rule 命中 → 走既有 `classifier/engine.py` 內建規則 → (3) 若皆無 → 寫入「未分類」 category。`manual_category_override` SHALL 保持 false（除非使用者自己編輯）。

#### Scenario: user rule 優先於 engine

- **WHEN** transaction.description = "UBER"、user rule（pattern="UBER", category=餐飲, priority=10）、engine 內建規則（UBER → 交通）
- **THEN** classify 結果 SHALL 為「餐飲」（user rule 勝出）、stage_summary 計入 `user_rule_hits`

#### Scenario: 多條 user rule 按 priority 排序

- **WHEN** rule A（priority=100, pattern="UBER", category=餐飲）、rule B（priority=50, pattern="UBER", category=交通）、description = "UBER EATS"
- **THEN** classify SHALL 命中 rule A 寫入「餐飲」，rule B 不評估

#### Scenario: enabled=false 的規則跳過

- **WHEN** user rule pattern="UBER" enabled=false 存在
- **THEN** classify SHALL 不評估該規則、走 engine 內建規則

#### Scenario: 無 user rule 命中走 engine

- **WHEN** description = "7-ELEVEN"、無 user rule 命中
- **THEN** classify SHALL 走 engine 內建規則（如歸類「便利商店」），stage_summary 計入 `engine_hits`

### Requirement: GET /api/rules 列出與 filter

系統 SHALL 提供 `GET /api/rules` 端點，回傳所有 rules 按 `priority DESC` 排序。支援 `?enabled=true|false` filter 與 `?category_id=` filter。

#### Scenario: 預設按 priority 排序

- **WHEN** 前端呼叫 `GET /api/rules`
- **THEN** response SHALL 為陣列、按 priority DESC 排序、含每 rule 完整欄位

#### Scenario: enabled filter

- **WHEN** `GET /api/rules?enabled=false`
- **THEN** SHALL 僅回 `enabled=false` 的 rules

### Requirement: POST/PUT/DELETE /api/rules CRUD

系統 SHALL 提供 `POST /api/rules`（建立）、`PUT /api/rules/{id}`（更新）、`DELETE /api/rules/{id}`（刪除）三個端點。建立時 priority 可選（預設 0）；更新為 partial update。

#### Scenario: 建立規則

- **WHEN** `POST /api/rules` body `{pattern: "STARBUCKS", pattern_type: "keyword", category_id: "cat_food", priority: 50}`
- **THEN** 系統 SHALL 建立 row、回 201 + 完整 rule 物件含 id

#### Scenario: 422 invalid pattern_type

- **WHEN** body `{pattern_type: "fuzzy"}`
- **THEN** SHALL 回 422 並錯誤訊息明示有效值為 keyword/exact/regex

#### Scenario: PUT partial update

- **WHEN** `PUT /api/rules/abc123` body `{enabled: false}`
- **THEN** SHALL 僅更新 enabled、其他欄位保留

#### Scenario: DELETE 後 classify 不再套用

- **WHEN** 刪除某 rule 後立即跑 pipeline
- **THEN** classify SHALL 不再考慮該規則，走後續規則 / engine

### Requirement: POST /api/rules/test 即時測試端點

系統 SHALL 提供 `POST /api/rules/test` 端點 body `{pattern, pattern_type, sample_text}`，回 `{matches: bool, error?: str}`。提供 UI 端「測試規則」即時預覽，使用者建立規則前可驗證 pattern 是否符合預期。

#### Scenario: 測試端點不寫入 DB

- **WHEN** 前端呼叫 test 端點
- **THEN** SHALL 僅執行 matcher 邏輯、不建立 / 修改任何 rule row

#### Scenario: regex 編譯錯誤回 error

- **WHEN** body `{pattern: "[invalid", pattern_type: "regex"}`
- **THEN** SHALL 回 200 含 `{matches: false, error: "regex 編譯失敗: ..."}`，不 raise 500

#### Scenario: regex timeout 也回 error

- **WHEN** test pattern 觸發 timeout
- **THEN** SHALL 回 `{matches: false, error: "匹配逾時（>100ms），請簡化 regex"}`

### Requirement: /settings/rules 前端頁面

系統 SHALL 提供 `frontend/src/pages/settings/rules.tsx`，路由 `/settings/rules`。頁面 SHALL 為表格（pattern / type / category / priority / enabled toggle / 操作）。「新增規則」對話框 SHALL 含 pattern input + type select + category select + priority + 「測試規則」即時預覽區塊。

#### Scenario: 「測試規則」即時預覽

- **WHEN** 使用者在新增對話框輸入 pattern、選 type、輸入 sample_text、點「測試」
- **THEN** UI SHALL 呼叫 `POST /api/rules/test`、即時顯示「✓ 命中」或「✗ 不命中」或「⚠️ regex 錯誤: ...」

#### Scenario: regex 複雜度警示

- **WHEN** 使用者輸入 nested quantifier pattern（如 `(a+)+`）
- **THEN** UI SHALL 在 pattern input 下方顯示橘色 banner「此 regex 含 nested quantifier，可能引發效能問題」

#### Scenario: 拖拉排序 priority

- **WHEN** 使用者拖拉表格 row 改順序
- **THEN** UI SHALL 自動計算新 priority 值（如反向插入位置）、批次送 PUT 更新；UI 樂觀更新先反映新順序

#### Scenario: 規則 enabled toggle

- **WHEN** 使用者點某 row 的 enabled switch
- **THEN** UI SHALL 立即送 PUT、樂觀更新；失敗 revert
