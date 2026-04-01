## MODIFIED Requirements

### Requirement: PipelineOptions 序列化

#### MODIFIED Scenario: 從 dict 反序列化
- **WHEN** 呼叫 `PipelineOptions.from_dict(data)` 且 `data` 型別為任意 `Mapping[str, object]`（包含 `dict[str, bool]` 等子型別）
- **THEN** 正確建立 `PipelineOptions` 實例，且 pyright strict mode 不報錯

### Requirement: 日期範圍計算

#### MODIFIED Scenario: 設定 month 但未設定 year 時使用當年
- **WHEN** 呼叫 `date_range()` 且 `month` 有值但 `year` 為 None
- **THEN** `effective_year` 自動設為當年，並以明確的 `ValueError` 防護（非 `assert`）

#### MODIFIED Scenario: 僅設定 year 時涵蓋全年
- **WHEN** 呼叫 `date_range()` 且 `year` 有值但 `month` 為 None
- **THEN** 回傳全年範圍，並以明確的 `ValueError` 防護（非 `assert`）
