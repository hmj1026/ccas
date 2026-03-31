# settings-page Specification

## Purpose
TBD - created by archiving change frontend-dashboard. Update Purpose after archive.
## Requirements
### Requirement: 提供銀行設定管理頁面
系統 SHALL 提供 Settings 頁面中的銀行設定區塊，讓使用者可檢視與修改 `bank_configs`，包含 `gmail_filter`、`pdf_password_rule`、`active_parser_version` 與 `is_active`。

#### Scenario: 更新銀行設定
- **WHEN** 使用者在 Settings 頁面編輯某家銀行設定並儲存
- **THEN** 系統會送出更新請求，並在成功後顯示最新銀行設定

### Requirement: 提供分類關鍵字管理頁面
系統 SHALL 提供 Settings 頁面中的分類規則區塊，讓使用者可新增、修改與刪除分類關鍵字映射。

#### Scenario: 新增分類關鍵字
- **WHEN** 使用者在 Settings 頁面新增一組 `keyword` 與 `category`
- **THEN** 頁面會送出建立請求，並在成功後顯示新的分類規則

#### Scenario: 刪除分類關鍵字
- **WHEN** 使用者在 Settings 頁面刪除某筆分類規則
- **THEN** 頁面會送出刪除請求，並在成功後從列表中移除該規則

