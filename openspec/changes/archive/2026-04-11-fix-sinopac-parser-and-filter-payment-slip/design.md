# Design

## Context

SINOPAC pipeline 端到端失敗。透過真實 PDF（`data/staging/SINOPAC/19ce64b14205_永豐銀行信用卡帳單.pdf` 等 58 封現代格式、1 封 2021 零額）逆向分析，確認現行 parser 是基於「理想樣本」撰寫的、未對真實 PDF 驗證。此次修正以實際 PDF 文字為單一事實來源（SSOT）。

## Decisions

### D1 — 黑名單型附件過濾（非 per-email 邏輯）

**方案**：在 `ingestor/filters.py` 定義 `ATTACHMENT_FILENAME_BLOCKLIST: dict[str, tuple[str, ...]]`，以 bank_code 對應 substring 黑名單；`_process_attachment` 在 dedupe 查詢前呼叫 `should_skip_attachment(bank_code, filename)`，命中時直接 `summary.skipped_count += 1` 並 return。

**替代方案**：擴充 `BankConfig` 加 `attachment_filename_blocklist` 欄位（需 migration）。
**捨棄理由**：只有 SINOPAC 需要此功能，欄位+migration+seed 的負擔大於收益；未來若有更多銀行需要，再升級為 DB 欄位。

### D2 — Parser 以實測 PDF 為唯一事實來源

所有 regex 與 table 解析邏輯都基於實際 PDF 文字樣本寫成，fixture 直接截取真實 PDF 片段（移除個資）。捨棄「規格文件樣本」式寫法。

### D3 — 零額歷史帳單以 skip 而非 failed 處理

`SinopacV1Parser.can_parse()` 仍回傳 True（檔案確實是永豐帳單），但 `parse()` 若偵測到 `無需繳款` 則拋出 `ParseError("zero-balance historical bill", reason="no due date / amount")`。在 `parser/job.py` 視情況 catch → 記為 skipped。

**風險**：若未來有其他合法零額帳單需保留，要改策略。  
**緩解**：目前全 DB 只有 1 筆符合此條件（2021-05），足夠取樣代表性；後續可改策略而不影響 schema。

## 實作順序

1. **Ingest filter**（T1-T2）：簡單、可先測。
2. **Parser 摘要**（T3）：修 due date + total amount。
3. **Parser 交易**（T4）：修表頭與 row 解析。
4. **零額帳單處理**（T5）。
5. **E2E 驗證**（T6）。
