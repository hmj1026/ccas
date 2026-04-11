# Tasks

## T1: Tests
- [x] T1.1 `conftest.py` 新增三組 CATHAY 真實 fixture（108/05、115/03、112/03）
- [x] T1.2 `test_cathay_v1.py` 新增 `TestRealPdfFormat` 覆蓋三種 summary 佈局
- [x] T1.3 `test_filters.py` 新增 CATHAY 繳款聯 blocklist scenario

## T2: Implementation
- [x] T2.1 `ingestor/filters.py` 新增 `CATHAY: ("繳款聯",)`
- [x] T2.2 `cathay_v1.py` `can_parse` 掃描全部頁面
- [x] T2.3 `cathay_v1.py` 新增 `_RE_DUE_DATE_PAREN`、`_RE_DUE_DATE_DEBIT`，`_extract_due_date` 後援
- [x] T2.4 `cathay_v1.py` 新增 `_RE_BILLING_MONTH_REAL`、`_RE_BILLING_MONTH_HEADER`，`_extract_billing_month` 後援

## T3: E2E
- [x] T3.1 Reset CATHAY staged_attachments 與檔案；重新 ingest（驗證 blocklist 生效）
- [x] T3.2 `uv run python -m ccas.pipeline --bank CATHAY --from parse` → failed=0
- [x] T3.3 `./scripts/dev-test.sh tests/unit` → all passed
- [x] T3.4 `./scripts/dev-lint.sh` → clean
