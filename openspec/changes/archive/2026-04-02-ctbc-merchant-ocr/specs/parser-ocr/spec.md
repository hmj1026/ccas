## ADDED Requirements

### Requirement: OCR 可用性偵測

系統 SHALL 提供 `is_ocr_available()` 函式偵測 tesseract 是否已安裝，結果在 process 生命週期內 cache。

#### Scenario: tesseract 已安裝
- **WHEN** 系統上已安裝 tesseract-ocr
- **THEN** `is_ocr_available()` SHALL 回傳 `True`

#### Scenario: tesseract 未安裝
- **WHEN** 系統上未安裝 tesseract-ocr
- **THEN** `is_ocr_available()` SHALL 回傳 `False`，並以 WARNING 等級記錄一次提示訊息

### Requirement: 圖片文字辨識

系統 SHALL 提供 `extract_text_from_image()` 函式，接受 PIL Image 並回傳辨識後的文字。

#### Scenario: 成功辨識
- **WHEN** 傳入清晰的中文文字圖片且 tesseract 可用
- **THEN** SHALL 回傳辨識後的文字字串，去除前後空白

#### Scenario: tesseract 不可用
- **WHEN** tesseract 未安裝且呼叫 `extract_text_from_image()`
- **THEN** SHALL 回傳空字串 `""`，不拋出例外

#### Scenario: 辨識失敗
- **WHEN** 圖片無法辨識或 OCR 過程發生錯誤
- **THEN** SHALL 回傳空字串 `""`，記錄 WARNING log
