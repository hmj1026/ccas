# settings-api Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
### Requirement: 提供銀行設定讀取與部分更新 API
系統 SHALL 提供 `bank_configs` 的讀取與有限更新 API。API 應支援：
- 讀取：`bank_code`、`bank_name`、`gmail_filter`、`active_parser_version`、`is_active`
- 更新：`is_active` 與 `active_parser_version` 欄位
- **刪除**：不提供 PDF 密碼規則的讀取或修改端點（密碼規則存放在 .env，不在 DB）

#### Scenario: 取得全部銀行設定
- **WHEN** 前端呼叫 `GET /api/settings/banks`
- **THEN** API 會回傳所有銀行設定資料（**不含** `pdf_password_rule`）

#### Scenario: 更新銀行設定啟用狀態或 parser 版本
- **WHEN** 前端送出 `PATCH /api/settings/banks/{id}` 並帶入 `{"is_active": false}` 或 `{"active_parser_version": "v2"}`
- **THEN** API 會更新對應欄位

#### Scenario: 嘗試修改 pdf_password_rule 返回錯誤
- **WHEN** 前端嘗試在 request body 中包含 `pdf_password_rule` 並送出 PATCH
- **THEN** API 會忽略該欄位或返回 400 Bad Request，說明密碼規則由環境變數管理

### Requirement: 提供分類關鍵字 CRUD API
系統 SHALL 提供 `categories` 的 CRUD API，至少支援讀取、建立、更新與刪除 `keyword` 與 `category`。

#### Scenario: 新增分類關鍵字
- **WHEN** 前端送出 `POST /api/settings/categories` 並帶入新的 `keyword` 與 `category`
- **THEN** API 會建立新的分類映射並回傳建立結果

#### Scenario: 刪除分類關鍵字
- **WHEN** 前端送出 `DELETE /api/settings/categories/{id}`
- **THEN** API 會刪除該分類映射，並讓後續分類流程不再使用它

