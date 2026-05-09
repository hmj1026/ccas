## MODIFIED Requirements

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
