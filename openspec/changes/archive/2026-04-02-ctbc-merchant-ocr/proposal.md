## Why

CTBC 真實帳單 PDF 的商戶名稱（消費明細載要欄位）以圖片渲染，pdfplumber 無法直接提取文字。目前 parser 將 merchant 預設為空字串，導致 classify 階段無法自動分類。經分析圖片品質清晰，OCR 可高準確率提取。

## What Changes

- 新增 `ccas.parser.ocr` 模組：封裝 tesseract OCR 可用性偵測與圖片文字辨識
- 修改 CTBC v1 parser ROC 格式解析：裁切每筆交易的商戶名稱圖片區域，送 OCR 辨識
- **Graceful fallback**: tesseract 未安裝時 merchant 仍為空字串，僅輸出一次 warning log
- 新增 `pytesseract` 依賴；Docker production image 加裝 `tesseract-ocr` + `chi_tra` 語言包

## Capabilities

### New Capabilities
- `parser-ocr`: OCR 封裝模組，偵測 tesseract 可用性、提供圖片文字辨識功能

### Modified Capabilities
- `ctbc-parser`: ROC 格式商戶名稱從空字串改為 OCR 提取（可選）

## Impact

- **Dependencies**: 新增 `pytesseract`（runtime）、`Pillow`（已有）
- **Docker**: production image 增加 ~80MB（tesseract + chi_tra）
- **Parser output**: merchant 欄位從 `""` 改為實際商戶名稱（tesseract 可用時）
- **Downstream**: classify 階段可正確分類 CTBC 交易
- **Breaking**: 無
