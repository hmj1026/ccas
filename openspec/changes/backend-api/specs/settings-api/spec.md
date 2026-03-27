## ADDED Requirements

### Requirement: 提供銀行設定 CRUD API
系統 SHALL 提供 `bank_configs` 的 CRUD API，至少支援讀取、建立與更新 `bank_code`、`bank_name`、`gmail_filter`、`pdf_password_rule`、`active_parser_version`、`is_active`。

#### Scenario: 取得全部銀行設定
- **WHEN** 前端呼叫 `GET /api/settings/banks`
- **THEN** API 會回傳所有銀行設定資料

#### Scenario: 更新銀行設定啟用狀態
- **WHEN** 前端送出 `PATCH /api/settings/banks/{id}` 並帶入 `{"is_active": false}`
- **THEN** API 會將對應銀行設定更新為停用

### Requirement: 提供分類關鍵字 CRUD API
系統 SHALL 提供 `categories` 的 CRUD API，至少支援讀取、建立、更新與刪除 `keyword` 與 `category`。

#### Scenario: 新增分類關鍵字
- **WHEN** 前端送出 `POST /api/settings/categories` 並帶入新的 `keyword` 與 `category`
- **THEN** API 會建立新的分類映射並回傳建立結果

#### Scenario: 刪除分類關鍵字
- **WHEN** 前端送出 `DELETE /api/settings/categories/{id}`
- **THEN** API 會刪除該分類映射，並讓後續分類流程不再使用它
