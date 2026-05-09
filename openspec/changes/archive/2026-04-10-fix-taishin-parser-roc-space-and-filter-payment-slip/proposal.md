# Proposal: Fix TAISHIN Parser (ROC Year w/o Colon) and Filter PaymentSlip

## Problem

`uv run python -m ccas.pipeline --bank TAISHIN` 結果：
- 59 個 `TSB_Creditcard_Estatement_*.pdf` 全部 parse_failed，錯誤為「找不到繳費截止日」
- 59 個 `TSB_PaymentSlip_*.pdf` 全部 parse_failed，錯誤為 `can_parse=False`（PaymentSlip 是繳款明細書，非帳單）
- 16 個最新 PDF（202601–202603）因密碼變更而 decrypt_failed（資料缺口，需使用者補充新密碼，不在此變更範圍）

根因檢視實際 PDF 後：
1. TAISHIN 使用民國年，且 `繳款截止日 113/11/27` 在標籤與日期之間**只有空白，沒有冒號**。`_RE_DUE_DATE` / `_RE_ROC_DUE_DATE` 要求 `[：:]` 字元，皆無法匹配。
2. PaymentSlip PDFs 是繳款聯／繳款明細，無帳單資料，應於 ingest 階段以檔名黑名單過濾（類似 SINOPAC 的 `繳款聯` 策略）。

## What Changes

- `backend/src/ccas/parser/banks/taishin_v1.py`：將 `_RE_DUE_DATE` / `_RE_ROC_DUE_DATE` 的冒號改為可選（`[：:]?\s*`）。
- `backend/src/ccas/ingestor/filters.py` 的 `ATTACHMENT_FILENAME_BLOCKLIST` 新增 `TAISHIN: ("PaymentSlip",)`。
- 新增 unit tests 覆蓋無冒號民國年格式。

## Impact

- Affected spec: `specs/taishin-parser/spec.md`、`specs/gmail-ingestion/spec.md`
- Affected code: `backend/src/ccas/parser/banks/taishin_v1.py`, `backend/src/ccas/ingestor/filters.py`
- Affected tests: `backend/tests/unit/parser/test_taishin_v1.py`, `backend/tests/unit/ingestor/test_filters.py`, `backend/tests/unit/parser/conftest.py`
- Out of scope: 16 筆 202601–202603 decrypt_failed（需使用者確認新密碼）
