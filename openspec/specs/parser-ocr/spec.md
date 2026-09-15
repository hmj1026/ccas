# parser-ocr Specification

## Purpose
TBD - created by archiving change ctbc-merchant-ocr. Update Purpose after archive.
## Requirements
### Requirement: OCR 可用性偵測

系統 SHALL 提供 `is_ocr_available()` 函式偵測 tesseract 是否已安裝，結果在 process 生命週期內 cache。

#### Scenario: tesseract 已安裝
- **WHEN** 系統上已安裝 tesseract-ocr
- **THEN** `is_ocr_available()` SHALL 回傳 `True`

#### Scenario: tesseract 未安裝
- **WHEN** 系統上未安裝 tesseract-ocr
- **THEN** `is_ocr_available()` SHALL 回傳 `False`，並以 WARNING 等級記錄一次提示訊息

### Requirement: 圖片文字辨識

系統 SHALL 提供 `extract_text_from_image()` 函式，接受 PIL Image 並回傳辨識後的文字；此函式 SHALL 同時被既有的 CTBC 帳單商家名稱圖片辨識路徑，以及新增的掃描件整頁 OCR fallback 路徑使用，兩者共用同一份底層辨識邏輯與 tesseract 可用性偵測。

#### Scenario: 成功辨識
- **WHEN** 傳入清晰的中文文字圖片且 tesseract 可用
- **THEN** SHALL 回傳辨識後的文字字串，去除前後空白

#### Scenario: tesseract 不可用
- **WHEN** tesseract 未安裝且呼叫 `extract_text_from_image()`
- **THEN** SHALL 回傳空字串 `""`，不拋出例外

#### Scenario: 辨識失敗
- **WHEN** 圖片無法辨識或 OCR 過程發生錯誤
- **THEN** SHALL 回傳空字串 `""`，記錄 WARNING log

### Requirement: 掃描件整頁 OCR 作為規則解析失敗後的 fallback

當文字層解析（既有銀行 parser 規則）判定某帳單附件為掃描件或無法取得文字層時，系統 SHALL 嘗試對整份 PDF 逐頁執行 OCR，產出可供後續規則式欄位擷取使用的文字內容，並標記該次解析結果 `parse_method="ocr"`。

#### Scenario: 純掃描件觸發整頁 OCR

- **WHEN** 某帳單附件沒有可抽取的文字層，且所有候選銀行 parser 的 `can_parse()` 皆因缺乏文字層而失敗
- **THEN** 系統 SHALL 對該附件執行整頁 OCR fallback，嘗試從辨識文字中擷取帳單欄位

#### Scenario: OCR fallback 仍失敗時退回既有失敗路徑

- **WHEN** 整頁 OCR fallback 執行後仍無法擷取出有效帳單欄位
- **THEN** OCR SHALL 回報沒有可採用的候選結果給 parse orchestration；若 LLM 參考開關已開啟，orchestration SHALL 先嘗試 LLM，否則才依既有行為將該附件標記 `parse_failed`，且不得讓 pipeline 因此中斷

#### Scenario: OCR 不可用時不阻斷規則解析路徑

- **WHEN** tesseract 未安裝（`is_ocr_available()` 回傳 `False`）且觸發掃描件 fallback 情境
- **THEN** OCR SHALL 回傳空結果並記錄原因；若 LLM 參考開關已開啟，parse orchestration SHALL 繼續嘗試 LLM，否則才標記該附件 `parse_failed`，既有文字層解析路徑（`parse_method="rules"`）SHALL 完全不受影響

