# Why

現行 SINOPAC 全部 59 封帳單在 `parse` 階段 100% 失敗（`[Parse] 帳單摘要缺失: 找不到繳費截止日`），同時每封郵件還附帶一個無用的 `永豐銀行信用卡繳款聯.pdf`（付款用繳款單、非帳單），被 ingest 後於 `parse` 階段失敗，污染統計與 DB。

根因分析（以真實 PDF 驗證）：

1. **Due date regex 誤要求冒號**：實際文字為 `您的繳款截止日2026/03/27`（無 `：`），而 `_RE_DUE_DATE = r"繳[費款]截止日[：:]\s*…"` 要求冒號。
2. **Total amount regex 無法對應表格列格式**：金額位於 `臺幣 7,147 7,147 12,579 0 0 12,579 1,311` 這行的第 6 欄（本期應繳總金額），不在 `應繳總金額` 關鍵字之後。
3. **Transaction regex 要求 YYYY/MM/DD**：實際交易行是 `02/18 02/24 4300 悠遊卡自動加值─台北捷 500`（MM/DD + 卡號末四碼 + 商戶 + 金額）。
4. **Table header 關鍵字不符**：`_TRANSACTION_HEADER_KEYWORDS = ("交易日", "金額")`，但實際表頭為 `入帳起息日 / 卡號末四碼 / 帳單說明 / 臺幣金額 / …`。
5. **零金額歷史帳單**：1 封 2021 年「無需繳款」帳單沒有 due_date 與 amount。
6. **繳款聯附件污染**：SINOPAC Gmail 郵件同時帶 `帳單.pdf`（part_id=1）與 `繳款聯.pdf`（part_id=2）；後者非帳單、無解析價值，應於 ingest 直接 skip。

# What Changes

- **Ingest**：新增每銀行附件檔名黑名單機制；SINOPAC 將 `繳款聯` 關鍵字列入黑名單，命中時 ingest SHALL skip 而非 stage。
- **SinopacV1Parser**：
  - `_RE_DUE_DATE` 改為冒號可選，新增支援 `您的繳款截止日YYYY/MM/DD` 無分隔格式。
  - `_extract_total_amount` 改為從 `臺幣` 開頭之摘要表列抽取第 6 個數字作為「本期應繳總金額」。
  - 交易擷取：放寬 `_TRANSACTION_HEADER_KEYWORDS` 為 `("入帳", "臺幣金額")`，row 解析支援 `MM/DD MM/DD 4digit merchant amount` 格式，ROC/西元年自動補齊。
  - `can_parse` 與 `parse` 對 `無需繳款` 零額帳單 SHALL 視為不可 parse（skip），以 `ParseError("zero-balance historical bill")` 拋出並於統計標記為 skipped（非 failed）。
- **測試**：新增 real-PDF fixture 的 parser unit test；新增 ingestor filename 黑名單 unit test。

# Impact

- **Affected specs**：`gmail-ingestion`（ADDED filename blocklist requirement）、`sinopac-parser`（MODIFIED 摘要與交易擷取、ADDED 零額帳單處理）。
- **Affected code**：
  - `backend/src/ccas/ingestor/job.py`（呼叫 filter）
  - `backend/src/ccas/ingestor/filters.py`（新檔，filename blocklist 常數與 helper）
  - `backend/src/ccas/parser/banks/sinopac_v1.py`
  - `backend/tests/unit/ingestor/test_filters.py`（新）
  - `backend/tests/unit/parser/test_sinopac_v1.py`
- **Breaking changes**：無。歷史已 staged 的 `繳款聯.pdf` 維持現狀（可由 dedupe script 清理）。
