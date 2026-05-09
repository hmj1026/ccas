## Context

CTBC 帳單 PDF 結構分析結果：每筆交易行在 x=125-217、y 與交易行對齊的位置有一張 92x9 像素的圖片，內容是商戶名稱。pdfplumber 可定位這些圖片位置，但無法讀取其文字內容。

目前 `_parse_roc_transaction()` 硬編碼 `merchant=""`。

## Goals / Non-Goals

**Goals:**
- OCR 提取 CTBC ROC 格式商戶名稱
- tesseract 不可用時 graceful fallback（不報錯、不 crash）
- 封裝 OCR 邏輯供未來其他銀行 parser 使用

**Non-Goals:**
- 不做通用 PDF OCR 框架
- 不處理 labeled 格式（已有 table extraction）
- 不改變 ParseResult/TransactionItem 資料結構

## Decisions

### D1: OCR 封裝為獨立模組 `ccas.parser.ocr`

提供兩個函式：
- `is_ocr_available() -> bool`：偵測 tesseract 是否已安裝（結果 cache，整個 process 只偵測一次）
- `extract_text_from_image(image: Image.Image, lang: str) -> str`：OCR 辨識，不可用時回傳 `""`

**替代方案**：直接在 ctbc_v1.py 內 inline 呼叫 pytesseract。
**否決原因**：未來其他銀行可能也需要 OCR，封裝利於複用。

### D2: 商戶圖片定位策略 — pdfplumber images metadata

每筆交易的 regex match 提供 y 座標。用 `page.images` 列表找出同一 y 範圍內、x=120-220 的圖片。裁切該區域送 OCR。

具體流程：
1. `_extract_transactions_roc()` 先蒐集 page.images 中 merchant 區域的圖片位置
2. 為每筆交易的 regex match 配對最近的商戶圖片（by y 座標）
3. 用 `page.crop((x0, y0, x1, y1)).to_image()` 裁切
4. 送 `extract_text_from_image()` OCR
5. 結果填入 `TransactionItem.merchant`

### D3: tesseract 不可用時的 fallback

- `is_ocr_available()` 在第一次呼叫時偵測，cache 結果
- 不可用時輸出一次 WARNING log（避免每筆交易都 log）
- merchant 設為 `""`（與目前行為一致）
- 不拋出例外

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| tesseract 未安裝時退化為現有行為 | 明確 log 提示安裝方式 |
| OCR 準確率不足 | 圖片品質清晰，實測後調整；可加 psm 參數最佳化 |
| 增加 parse 時間 | 每筆 ~0.3s，15 筆交易 ~5s，可接受 |
| Docker image 變大 | ~80MB，production stage only |
