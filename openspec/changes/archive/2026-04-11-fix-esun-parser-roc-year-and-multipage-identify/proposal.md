# Proposal: Fix ESUN Parser (ROC Year, Multi-page Identify, TWD Currency)

## Problem

執行 `uv run python -m ccas.pipeline --bank ESUN` 時，37 份 ESUN PDF 全數 `can_parse=False`。實際原因經由檢視 PDF 文字後歸納如下：

1. **首頁不包含 `玉山銀行` 字串**：首頁僅見 `信用卡帳單` 與 `玉山Wallet App`；`玉山銀行` 四字只在第 3 頁的扣款說明中出現。`SinopacV1Parser._identify` 與 `EsunV1Parser._identify` 只掃第 0 頁，導致 can_parse=False。
2. **民國年帳單月份**：首頁標題格式為 `這是您 115年02月 信用卡帳單`，現有 `_RE_BILLING_MONTH`（要求 4 位數西元年）無法匹配。
3. **繳款截止日無標籤、使用民國年**：首頁第 5 行為 `115/04/07 7.88%`，無「繳款截止日：」前綴，現有 `_RE_DUE_DATE` 要求該標籤而失敗。
4. **本期應繳金額使用 TWD 前綴**：頁 2 為 `本期應繳總金額： TWD 26,920`，現有 `_RE_TOTAL_AMOUNT` 只支援 `NT$` 前綴。
5. **交易行格式為 MM/DD MM/DD MERCHANT TWD AMOUNT**：與現有 `_RE_TRANSACTION_LINE` 要求 `YYYY/MM/DD` 日期不符。

## What Changes

- 擴大 `EsunV1Parser._identify` 至全部頁面（合併文本後檢查）。
- 新增民國年 billing_month pattern：`這是您\s*(\d{2,3})年(\d{1,2})月\s*信用卡帳單`，優先匹配。
- 新增無標籤 due_date pattern：`(\d{2,3})/(\d{1,2})/(\d{1,2})\s+\d+\.\d+%`（抓緊接著利率的日期行）。
- `_RE_TOTAL_AMOUNT` 支援 `TWD` 前綴：`(?:NT\$?|TWD)?`。
- 新增 ESUN-flavored transaction pattern：`(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})\s+(.+?)\s+TWD\s+(-?[\d,]+)`。
- 新增 unit tests 覆蓋真實 PDF 文字樣本（ROC year, TWD prefix, multi-page identify）。

## Impact

- Affected spec: `specs/esun-parser/spec.md`（MODIFIED identify/summary/transaction 行為）
- Affected code: `backend/src/ccas/parser/banks/esun_v1.py`
- Affected tests: `backend/tests/unit/parser/test_esun_v1.py`, `backend/tests/unit/parser/conftest.py`
