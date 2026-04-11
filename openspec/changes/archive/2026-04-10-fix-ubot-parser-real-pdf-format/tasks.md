# Tasks

## T1: Test fixtures
- [x] T1.1 `backend/tests/unit/parser/conftest.py`：新增 `UBOT_REAL_SUMMARY_TEXT`、`UBOT_REAL_ZERO_BALANCE_TEXT`、`UBOT_REAL_TRANSACTIONS_TEXT` 與期望值
- [x] T1.2 新增 `TestRealPdfFormat` 類別測試：summary 三欄位、zero-balance、本地/外幣/行動支付/退款/卡號追蹤/整合

## T2: Parser implementation
- [x] T2.1 新增真實 PDF 錨點 regex：`_RE_UBOT_MONTH_REAL`、`_RE_UBOT_CLOSE_DATE`、`_RE_UBOT_DUE_REAL`、`_RE_UBOT_TOTAL_REAL`
- [x] T2.2 `_extract_billing_month`：真實格式優先（月份 + 結帳日 ROC 年）
- [x] T2.3 `_extract_due_date`：真實格式優先（`已申請自動轉帳` 錨點）
- [x] T2.4 `_extract_total_amount`：真實格式優先（`優惠注意事項` 首欄）
- [x] T2.5 `_extract_summary`：「無需繳款」→ ParseError(zero-balance)
- [x] T2.6 新增 `_RE_UBOT_TXN_REAL`、`_RE_UBOT_CARD_HEADER`、`_parse_mmdd_loose`
- [x] T2.7 新增 `_extract_transactions_real`，掛入 `_extract_transactions` fallback chain
- [x] T2.8 `_identify` 加入 `_UBOT_KEYWORDS_REAL` 分支（處理新版 PDF 無「聯邦銀行」header）
- [x] T2.9 `can_parse` 掃描全部頁面文字而非僅 page 0

## T3: E2E verification
- [x] T3.1 Reset UBOT `parse_failed → decrypted`
- [x] T3.2 `uv run python -m ccas.pipeline --bank UBOT --from parse` → parsed=33, skipped=1, failed=0; classified=381
- [x] T3.3 `./scripts/dev-test.sh tests/unit tests/integration --ignore=tests/integration/parser` → 814 passed
- [x] T3.4 `./scripts/dev-lint.sh` → clean
