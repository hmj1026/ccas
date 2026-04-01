## Context

CCAS pipeline 有三層去重（ingestion, parse, notify），預設行為避免重複下載與處理。但使用者無法在更新密碼、修正 parser、或需要重處理特定帳單時繞過去重。CLI 和 API 都不支援任何參數。

現有架構：
- `run_pipeline(session)` → `run_ingestion_job(session)` → `run_parse_job(session)` → ...
- 各階段函式只接受 `session`，無法傳遞執行選項
- CLI (`__main__.py`) 無 argparse，API endpoint 無 request body

## Goals / Non-Goals

**Goals:**
- 新增 `PipelineOptions` 作為 pipeline 參數載體，貫穿 orchestrator 到各階段
- CLI 支援 `--force`、`--bank`、`--year`、`--month`
- API 支援等效的 JSON body 參數
- Force 模式下刪除舊記錄再重新下載/解析
- 日期篩選透過 Gmail query syntax 在 API 層面過濾
- 預設行為（無參數）完全不變

**Non-Goals:**
- 不改變 decrypt / classify / notify 階段的邏輯（force 效果透過 ingestion + parse 層自動傳遞）
- 不新增資料庫 migration（所有改動在 Python 程式碼層面）
- 不實作 dry-run 模式（未來可擴展）
- 不處理跨銀行的批次 force（一次只指定一個 bank_code 或全部）

## Decisions

### D1: 引入 frozen dataclass `PipelineOptions` 而非散裝參數

**選擇**: 建立 `PipelineOptions(force, bank_code, year, month)` frozen dataclass

**替代方案**: 在各函式簽名加入 `force: bool = False, bank_code: str | None = None, ...`

**理由**: dataclass 提供單一型別、易於序列化（API → RQ worker）、未來可擴展（如 dry_run、stages）。散裝參數在 5+ 個函式間傳遞會導致簽名膨脹。

### D2: Force 模式採用「刪除舊記錄再重建」策略

**選擇**: 發現已存在的 `StagedAttachment` 時，先刪除再重新下載建立新記錄

**替代方案 A**: Update-in-place（更新現有記錄的 file path 和 status）
**替代方案 B**: 跳過 DB 約束檢查但不插入重複

**理由**: 刪除再重建最乾淨——所有欄位（timestamps, error_reason, staged_path）都從頭開始，避免部分狀態 bug。unique constraint 天然滿足（先刪後插）。parse 層同理：刪除舊 Bill（cascade 刪除 Transactions）再重新 parse。

### D3: 日期篩選透過 Gmail query syntax 實作

**選擇**: 在 `PipelineOptions.gmail_date_filter()` 方法產生 `after:YYYY/MM/DD before:YYYY/MM/DD`，附加到 bank 的 `gmail_filter`

**替代方案**: 下載所有郵件後在 Python 層面按日期過濾

**理由**: Gmail API 層面過濾減少網路傳輸和 API quota 消耗。Gmail query syntax 原生支援 `after:` / `before:`（日期為 exclusive）。

### D4: `options` 參數預設 `None` 以保持向後相容

**選擇**: `run_pipeline(session, options=None)`，`None` 等同 `PipelineOptions()` 預設值

**理由**: 所有現有呼叫端（scheduler、worker）不需修改即可正常運作。只有 CLI 和 API 端新增 options 建構邏輯。

### D5: API endpoint 使用 Optional body 而非 query params

**選擇**: `POST /api/pipeline/trigger` 接受 `PipelineTriggerRequest | None` body

**替代方案**: 使用 query parameters `?force=true&bank=CTBC`

**理由**: POST body 語意更正確（觸發 pipeline 是一個 mutation），且 body 更適合未來擴展（如傳入 stages 列表）。空 body 等同預設行為，向後相容。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Force 模式刪除 Bill cascade 刪除 Transactions，資料不可逆 | CLI 加入確認提示；API 呼叫端應自行管控；force 是 opt-in 旗標 |
| Gmail date filter 的月份邊界計算可能有 off-by-one | `gmail_date_filter()` 需完善的 unit test 覆蓋閏年、12 月跨年等邊界案例 |
| 兩次 force run 同時執行可能 race condition | RQ queue 序列化 job 執行；CLI 為手動操作不太可能同時觸發 |
| Gmail API quota 在 force 大量重下載時可能耗盡 | 現有 `call_with_retry` 處理 429 和 5xx；quota 問題是既有風險，非此變更引入 |
