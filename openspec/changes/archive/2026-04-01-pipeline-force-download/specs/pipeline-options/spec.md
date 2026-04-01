## ADDED Requirements

### Requirement: PipelineOptions 資料模型
系統 SHALL 提供一個不可變的 `PipelineOptions` 資料模型，包含以下欄位，所有欄位皆有預設值：
- `force: bool = False` — 是否繞過去重強制重新處理
- `bank_code: str | None = None` — 僅處理指定銀行（None 表示全部）
- `year: int | None = None` — 篩選年份
- `month: int | None = None` — 篩選月份

#### Scenario: 預設建構
- **WHEN** `PipelineOptions()` 被建構且不帶任何參數
- **THEN** `force` 為 `False`，`bank_code`、`year`、`month` 皆為 `None`

#### Scenario: 指定部分參數
- **WHEN** `PipelineOptions(force=True, bank_code="CTBC")` 被建構
- **THEN** `force` 為 `True`，`bank_code` 為 `"CTBC"`，`year` 和 `month` 為 `None`

### Requirement: Gmail 日期篩選子句產生
`PipelineOptions` SHALL 提供 `gmail_date_filter()` 方法，根據 `year` 和 `month` 產生 Gmail 查詢日期篩選子句。

#### Scenario: 無年月時回傳空字串
- **WHEN** `year` 和 `month` 皆為 `None`
- **THEN** `gmail_date_filter()` 回傳 `""`

#### Scenario: 指定年月時回傳 after/before 子句
- **WHEN** `year=2026` 且 `month=3`
- **THEN** `gmail_date_filter()` 回傳 `"after:2026/02/28 before:2026/04/01"`

#### Scenario: 僅指定年份時篩選整年
- **WHEN** `year=2026` 且 `month` 為 `None`
- **THEN** `gmail_date_filter()` 回傳 `"after:2025/12/31 before:2027/01/01"`

#### Scenario: 僅指定月份時自動採用當年
- **WHEN** `month=3` 且 `year` 為 `None`
- **THEN** `gmail_date_filter()` 使用當前年份計算 after/before 子句

#### Scenario: 12 月跨年邊界正確處理
- **WHEN** `year=2026` 且 `month=12`
- **THEN** `gmail_date_filter()` 回傳 `"after:2026/11/30 before:2027/01/01"`

### Requirement: CLI 參數支援
`python -m ccas.pipeline` SHALL 支援以下 CLI 參數：
- `--force` — 啟用強制重新處理模式
- `--bank BANK_CODE` — 僅處理指定銀行
- `--year YYYY` — 篩選年份
- `--month MM` — 篩選月份（1-12）

#### Scenario: 無參數時維持預設行為
- **WHEN** 執行 `python -m ccas.pipeline` 且不帶任何參數
- **THEN** pipeline 以 `PipelineOptions()` 預設值執行，行為與變更前完全一致

#### Scenario: 組合參數
- **WHEN** 執行 `python -m ccas.pipeline --force --bank CTBC --year 2026 --month 3`
- **THEN** pipeline 以 `PipelineOptions(force=True, bank_code="CTBC", year=2026, month=3)` 執行

### Requirement: API 端點參數支援
`POST /api/pipeline/trigger` SHALL 接受可選的 JSON body，包含 `force`、`bank_code`、`year`、`month` 欄位。

#### Scenario: 空 body 維持預設行為
- **WHEN** `POST /api/pipeline/trigger` 不帶 body 或帶空 JSON `{}`
- **THEN** pipeline 以預設 `PipelineOptions()` 執行

#### Scenario: 帶參數的 body
- **WHEN** `POST /api/pipeline/trigger` body 為 `{"force": true, "bank_code": "CTBC"}`
- **THEN** pipeline 以 `PipelineOptions(force=True, bank_code="CTBC")` 執行
