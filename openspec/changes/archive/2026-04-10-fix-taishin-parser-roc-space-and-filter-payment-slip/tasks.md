# Tasks

## T1: 擴充 Filter 黑名單
- [x] T1.1 `backend/src/ccas/ingestor/filters.py`：`ATTACHMENT_FILENAME_BLOCKLIST` 新增 `"TAISHIN": ("PaymentSlip",)`
- [x] T1.2 `backend/tests/unit/ingestor/test_filters.py` 新增 TAISHIN scenario

## T2: TAISHIN Parser 冒號可選 + 真實格式支援
- [x] T2.1 `backend/src/ccas/parser/banks/taishin_v1.py`：`_RE_DUE_DATE` / `_RE_ROC_DUE_DATE` 改為 `[：:]?\s*`
- [x] T2.2 `backend/tests/unit/parser/test_taishin_v1.py` 新增無冒號 due_date 測試
- [x] T2.3 新增 `_RE_TOTAL_AMOUNT_REAL` 優先匹配「本期累計應繳金額」，避免誤抓「上期應繳總額」
- [x] T2.4 新增 `_RE_TAISHIN_TXN_REAL` 與 `_extract_transactions_real`：支援 ROC 年日期、FX 尾綴、國別碼、負數金額
- [x] T2.5 `_RE_TAISHIN_CARD_LAST4` 追蹤卡號末四碼 header 並綁定到後續交易
- [x] T2.6 `backend/tests/unit/parser/conftest.py` 新增 `TAISHIN_REAL_*` fixtures
- [x] T2.7 `TestRealPdfFormat` 測試類別（6 測試）覆蓋 summary / transactions / card_last4

## T3: E2E 驗證
- [x] T3.1 刪除 `TSB_PaymentSlip_*` 記錄（75 筆）與檔案；Reset TAISHIN `parse_failed → decrypted`（59 筆）
- [x] T3.2 `uv run python -m ccas.pipeline --bank TAISHIN --from parse` → parsed=59, classified=622, failed=0
- [x] T3.3 `./scripts/dev-test.sh tests/unit tests/integration --ignore=tests/integration/parser` → 806 passed
- [x] T3.4 Out of scope：16 筆 202601–202603 decrypt_failed 列為資料缺口（密碼無法解開新版加密）
