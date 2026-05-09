# Tasks

## T1: 測試樣本
- [x] T1.1 `backend/tests/unit/parser/conftest.py` 新增 ESUN 真實 PDF 文字 fixtures：`ESUN_REAL_PAGE0_TEXT`, `ESUN_REAL_PAGE1_TEXT`（含交易行）、`EXPECTED_ESUN_REAL_BILLING_MONTH='2026-02'`, `EXPECTED_ESUN_REAL_DUE_DATE=date(2026,4,7)`, `EXPECTED_ESUN_REAL_TOTAL_AMOUNT=26920`

## T2: `_identify` 全頁面掃描
- [x] T2.1 `EsunV1Parser.can_parse` 改為讀取所有頁面串接 text 再呼叫 `_identify`
- [x] T2.2 Unit test：首頁無「玉山」、第 3 頁有則回傳 True

## T3: 民國年 billing_month + due_date
- [x] T3.1 新增 `_RE_ESUN_REAL_BILLING = re.compile(r"這是您\s*(\d{2,3})年(\d{1,2})月\s*信用卡帳單")`（優先於舊 pattern）
- [x] T3.2 新增 `_RE_ESUN_REAL_DUE_DATE = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})\s+\d+\.\d+%")`（fallback 於有標籤 regex）
- [x] T3.3 `_extract_summary` 於現有 regex 之前嘗試新 pattern；民國年 → year + 1911
- [x] T3.4 Unit test：`115年02月` → `2026-02`；`115/04/07 7.88%` → `date(2026,4,7)`

## T4: TWD 前綴總金額
- [x] T4.1 `_RE_TOTAL_AMOUNT` 改為支援 `(?:NT\$?|TWD)?\s*` 前綴
- [x] T4.2 Unit test：`本期應繳總金額： TWD 26,920` → 26920

## T5: MM/DD 交易格式
- [x] T5.1 新增 `_RE_ESUN_TXN_LINE = re.compile(r"^(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})\s+(.+?)\s+TWD\s+(-?[\d,]+)\s*$", re.MULTILINE)`
- [x] T5.2 `_extract_transactions_text` 優先嘗試新 regex，fallback 舊的
- [x] T5.3 Unit test：正常消費行、退款負額行

## T6: E2E
- [x] T6.1 `cd backend && uv run python -m ccas.pipeline --bank ESUN --to parse` 全部 parsed，0 failed
- [x] T6.2 `./scripts/dev-lint.sh` + `./scripts/dev-test.sh tests/unit tests/integration --ignore=tests/integration/parser` 綠
- [x] T6.3 `sqlite3 data/ccas.db "SELECT COUNT(*) FROM bills WHERE bank_code='ESUN';"` ≥ 30
