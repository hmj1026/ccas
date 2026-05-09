## 1. OCR 模組

- [x] 1.1 新增 `pytesseract` 依賴至 `pyproject.toml`
- [x] 1.2 建立 `ccas/parser/ocr.py`：`is_ocr_available()` + `extract_text_from_image()`
- [x] 1.3 撰寫 `tests/unit/parser/test_ocr.py` unit tests

## 2. CTBC Parser 修改

- [x] 2.1 修改 `_extract_transactions_roc()` 加入商戶圖片定位與 OCR
- [x] 2.2 修改 `_parse_roc_transaction()` 接受 merchant 參數
- [x] 2.3 更新既有 CTBC parser unit tests

## 3. Docker

- [x] 3.1 更新 `backend/Dockerfile` production stage 加裝 tesseract-ocr + chi_tra

## 4. 驗證

- [x] 4.1 用真實 CTBC PDF 驗證 OCR 結果（需安裝 tesseract）
