---
paths:
  - "**/parser/**/*.py"
  - "**/parser/banks/**"
  - "config/banks.yaml"
---
# CCAS Bank Parser 開發慣例

## Architecture

- **Registry Pattern**: 全域 `registry` 單例（`parser/registry.py`），每個 parser 在模組底部呼叫 `registry.register(XxxV1Parser())` 自動註冊
- **ABC**: 繼承 `BankParser`（`parser/base.py`），實作 `can_parse(pdf_path) -> bool` 與 `parse(pdf_path) -> ParseResult`
- **命名**: `banks/<bank_code>_v<N>.py`（如 `ctbc_v1.py`），class 為 `<Bank>V<N>Parser`
- **Import**: 在 `banks/__init__.py` import 新模組以觸發自動註冊

## ParseResult Contract

- `ParseResult`（`parser/result.py`）：`bank_code`, `billing_month`（"YYYY-MM"）, `total_amount`（整數元）, `due_date`, `transactions`（tuple of `TransactionItem`）
- `TransactionItem`：`trans_date`, `merchant`, `amount`（整數元）, 可選 `posting_date`, `currency`, `original_amount`, `card_last4`, `installment_current/total`
- 金額為整數元（非分），由 orchestrator 持久化時轉換

## 新增 Parser 步驟

1. 建立 `banks/<bank_code>_v1.py`，設定 `bank_code` 與 `version` 類屬性
2. 實作 `can_parse()`：用 pdfplumber 檢查首頁特徵文字
3. 實作 `parse()`：提取帳單摘要 + 交易明細，回傳 `ParseResult`
4. 模組底部加 `registry.register(<Bank>V1Parser())`
5. 在 `banks/__init__.py` 加 import
6. 在 `config/banks.yaml` 加銀行設定
7. 測試：unit test 用 fixture PDF，integration test 走完整 parse job

## 常見 Parser 工具

- **pdfplumber**: 大多數 parser 的主力（`extract_tables()`, `extract_text()`）
- **OCR fallback**: 掃描件用 `parser/ocr.py`（pytesseract），需 tesseract 系統套件
- **regex**: 用於抽取日期、金額、分期資訊

## 測試模式

- Unit test: `tests/unit/parser/banks/test_<bank>_v1.py`，mock PDF 或 fixture 檔案
- Integration test: `tests/integration/parser/`，測完整 parse job 流程
- 用 `registry.clear()` 在 test fixture 中隔離 registry 狀態
