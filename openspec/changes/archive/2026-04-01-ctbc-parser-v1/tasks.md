## 1. 測試基礎建設 (TDD: RED)

- [x] 1.1 新增 `backend/tests/unit/parser/conftest.py`：CTBC 帳單文字 fixture（摘要文字、交易表格行、外幣行、分期行）+ `autouse` registry reset fixture 確保測試隔離
- [x] 1.2 新增 `backend/tests/unit/parser/test_ctbc_v1.py`：單元測試涵蓋 _identify、_extract_summary、_extract_transactions、錯誤情況
- [x] 1.3 新增 `backend/tests/integration/parser/test_ctbc_v1_pdf.py`：使用合成 PDF 的整合測試

## 2. Parser 核心實作 (TDD: GREEN)

- [x] 2.1 新增 `backend/src/ccas/parser/banks/ctbc_v1.py`：CtbcV1Parser 類別實作（can_parse, parse, _identify, _extract_summary, _extract_transactions）
- [x] 2.2 更新 `backend/src/ccas/parser/banks/__init__.py`：加入 `import ccas.parser.banks.ctbc_v1`
- [x] 2.3 確認所有測試通過

## 3. 多頁與邊界情況

- [x] 3.1 多頁表格處理：跨頁時延續交易明細解析
- [x] 3.2 錯誤處理：帳單摘要缺失時 raise ParseError，交易行解析失敗時 log warning 並跳過

## 4. Registry 整合與驗證

- [x] 4.1 更新 `config/bank-code-registry.yaml` 中 CTBC 的 `supported` 為 `true`，同時更新 `notes` 為適當描述（如「支援 v1 parser，可自動解析表格式帳單」）
- [x] 4.2 新增整合測試：驗證 import banks 後 registry 可 resolve CTBC v1 parser
- [x] 4.3 執行完整測試套件，確認 ctbc_v1.py 覆蓋率 >= 80%
- [x] 4.4 執行 `ruff check` + `ruff format` + `pyright` 通過
