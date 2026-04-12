## MODIFIED Requirements

### Requirement: Categories YAML 作為預設分類規則 SSOT

The system SHALL provide a `config/categories.yaml` file as the single source of truth for default keyword→category classification rules. The file SHALL list categories with nested keyword arrays and be consumed by a dedicated seed CLI to populate the `categories` database table.

#### Scenario: YAML 結構

- **WHEN** `config/categories.yaml` 被讀取
- **THEN** 檔案 SHALL 包含頂層 `categories:` list，每個 item 具有 `category: <str>` 與 `keywords: [<str>, ...]` 兩個��要欄位

#### Scenario: 至少涵蓋 9 類（含保險）

- **WHEN** `categories.yaml` 被讀取
- **THEN** 檔案 SHALL 至少包含「餐飲、交通、購物、娛樂、帳單水電、訂閱服務、超商、咖啡、保險」9 個 category 的 keyword list

#### Scenario: 保險類包含常見保險公司 keyword

- **WHEN** 檢查「保險」category 的 keywords
- **THEN** SHALL 至少包含「富邦產物保險」、「國泰產險」、「新光產險」等常見保險公司名稱
