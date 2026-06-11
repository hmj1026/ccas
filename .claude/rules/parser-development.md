---
paths:
  - "**/parser/**/*.py"
  - "**/parser/banks/**"
  - "config/banks.yaml"
---
# CCAS Bank Parser Conventions

## Architecture

- **Registry Pattern**: global `registry` singleton (`parser/registry.py`); each parser calls `registry.register(XxxV1Parser())` at module bottom for automatic registration
- **ABC**: inherit `BankParser` (`parser/base.py`), implement `can_parse(pdf_path) -> bool` and `parse(pdf_path) -> ParseResult`
- **Naming**: `banks/<bank_code>_v<N>.py` (e.g., `ctbc_v1.py`), class is `<Bank>V<N>Parser`
- **Import**: add new module import to `banks/__init__.py` to trigger auto-registration

## ParseResult Contract

- `ParseResult` (`parser/result.py`): `bank_code`, `billing_month` ("YYYY-MM"), `total_amount` (integer, NTD), `due_date`, `transactions` (tuple of `TransactionItem`)
- `TransactionItem`: `trans_date`, `merchant`, `amount` (integer, NTD), optional `posting_date`, `currency`, `original_amount`, `card_last4`, `installment_current/total`
- 全系統金額以 NTD 整數元儲存，不乘 100：amounts are integer NTD 元 end-to-end; the orchestrator persists them as-is (no unit conversion)

## Adding a Parser

1. Create `banks/<bank_code>_v1.py`, set `bank_code` and `version` class attributes
2. Implement `can_parse()`: use pdfplumber to check first-page signature text
3. Implement `parse()`: extract billing summary + transaction details, return `ParseResult`
4. Add `registry.register(<Bank>V1Parser())` at module bottom
5. Add import to `banks/__init__.py`
6. Add bank config to `config/banks.yaml`
7. Tests: unit test with fixture PDF, integration test through full parse job

## Common Parser Tools

- **pdfplumber**: primary tool for most parsers (`extract_tables()`, `extract_text()`)
- **OCR fallback**: scanned documents use `parser/ocr.py` (pytesseract), requires tesseract system package
- **regex**: for extracting dates, amounts, installment info

## Test Patterns

- Unit test: `tests/unit/parser/banks/test_<bank>_v1.py` — mock PDF or fixture file
- Integration test: `tests/integration/parser/` — full parse job flow
- Use `registry.clear()` in test fixture to isolate registry state
