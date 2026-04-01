## Why

CCAS 的 parser 框架（BankParser 抽象介面、ParseResult 資料結構、registry、parse job）已完整就緒，但 `parser/banks/` 目錄為空，沒有任何銀行的實際 parser 實作。中國信託 (CTBC) 是台灣最大的信用卡發卡行，作為第一個 parser 實作目標，可驗證整個 pipeline 從 PDF 解析到資料庫寫入的端對端流程。

## What Changes

- 新增 `backend/src/ccas/parser/banks/ctbc_v1.py`：CTBC v1 parser，使用 pdfplumber 解析表格式帳單 PDF
- 更新 `backend/src/ccas/parser/banks/__init__.py`：import ctbc_v1 模組以觸發 registry 註冊
- 新增單元測試與整合測試
- 更新 `config/bank-code-registry.yaml` 中 CTBC 的 `supported` 為 `true`

## Capabilities

### New Capabilities

- `ctbc-parser`: 中國信託信用卡帳單 PDF 解析能力，涵蓋格式辨識、帳單摘要提取、交易明細提取

### Modified Capabilities

- `parser-registry`: 新增 CTBC v1 parser 的自動註冊機制（banks/__init__.py import 觸發）

## Impact

- `backend/src/ccas/parser/banks/` -- 從空目錄變為包含第一個 parser 實作
- `backend/tests/unit/parser/` -- 新增 CTBC parser 單元測試與 fixture
- `backend/tests/integration/parser/` -- 新增 CTBC parser 整合測試
- `config/bank-code-registry.yaml` -- CTBC supported flag 變更
- 依賴：pdfplumber（已在 pyproject.toml 中）
