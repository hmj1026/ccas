# pipeline-options Specification

## Purpose
TBD - created by archiving change pipeline-force-download. Update Purpose after archive.
## Requirements
### Requirement: PipelineOptions 資料模型

`PipelineOptions` SHALL 提供 `from_dict()` 與 `to_dict()` 方法，支援與 `Mapping[str, object]` 之間的序列化與反序列化；`from_dict()` MUST 接受 `dict[str, bool]` 等 `Mapping` 子型別，且在 pyright strict mode 下不得產生型別錯誤。

#### MODIFIED Scenario: 從 dict 反序列化
- **WHEN** 呼叫 `PipelineOptions.from_dict(data)` 且 `data` 型別為任意 `Mapping[str, object]`（包含 `dict[str, bool]` 等子型別）
- **THEN** 正確建立 `PipelineOptions` 實例，且 pyright strict mode 不報錯

### Requirement: Gmail 日期篩選子句產生

`PipelineOptions` SHALL 提供 `date_range()` 方法，根據 `year` 和 `month` 計算起訖日期範圍，並以明確的 `ValueError` 防護無效輸入（非 `assert`）；當僅提供 `month` 時 SHALL 自動採用當年，當僅提供 `year` 時 SHALL 回傳全年範圍。

#### MODIFIED Scenario: 設定 month 但未設定 year 時使用當年
- **WHEN** 呼叫 `date_range()` 且 `month` 有值但 `year` 為 None
- **THEN** `effective_year` 自動設為當年，並以明確的 `ValueError` 防護（非 `assert`）

#### MODIFIED Scenario: 僅設定 year 時涵蓋全年
- **WHEN** 呼叫 `date_range()` 且 `year` 有值但 `month` 為 None
- **THEN** 回傳全年範圍，並以明確的 `ValueError` 防護（非 `assert`）

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

