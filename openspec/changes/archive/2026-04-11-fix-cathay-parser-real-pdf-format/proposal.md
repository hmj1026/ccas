# Fix CATHAY Parser Real PDF Format

## Why
Run A on CATHAY 顯示 173 個 staged 附件中 173 個 parse_failed，原因：
1. **can_parse=False（147/173）**：真實國泰世華 PDF 第一頁因 CID 字型編碼無法 extract「國泰世華」關鍵字，但其他頁面可辨識
2. **繳款聯付款憑證被 ingest（66/173）**：`國泰世華YYY年MM月信用卡繳款聯.pdf` 並非帳單，污染 staging
3. **找不到繳費截止日**：真實 PDF 使用 `繳款截止日(遇假日順延) 108/06/01`（無冒號）或 `帳款將於 115/04/01`，現行 regex 僅支援 `繳款截止日：`
4. **找不到帳單月份（新版 PDF）**：部分新版 PDF 以 `以下為您108年5月份的信用卡電子帳單` 或 `信用卡帳單 115年3月` 為月份錨點

## What Changes
- **ingestor/filters.py**：`ATTACHMENT_FILENAME_BLOCKLIST["CATHAY"]` 新增 `("繳款聯",)`
- **cathay_v1.py `can_parse`**：掃描全部頁面文字而非僅 page 0
- **cathay_v1.py `_extract_due_date`**：新增 `繳款截止日(遇假日順延) ROC/MM/DD` 與 `帳款將於 ROC/MM/DD` 錨點
- **cathay_v1.py `_extract_billing_month`**：新增 `以下為您(YYY)年(MM)月份` 與 `信用卡帳單 (YYY)年(MM)月` 錨點

## Impact
- specs: `cathay-parser`（MODIFIED can_parse、summary extraction）、`gmail-ingestion`（新增 CATHAY 黑名單）
- code: `backend/src/ccas/parser/banks/cathay_v1.py`、`backend/src/ccas/ingestor/filters.py`
- tests: `backend/tests/unit/parser/test_cathay_v1.py`、`backend/tests/unit/parser/conftest.py`、`backend/tests/unit/ingestor/test_filters.py`
