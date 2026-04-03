## ADDED Requirements

### Requirement: Parse 失敗結構化 logging

系統 SHALL 在 parser 處理附件失敗時輸出結構化日誌，包含足夠的診斷資訊以協助排查和改進 parser。

#### Scenario: Parse 失敗記錄 PDF 檔名與錯誤原因

- **WHEN** 某個 PDF 附件 parse 失敗
- **THEN** 系統 SHALL 以 ERROR 等級記錄日誌，包含：`pdf_filename`（PDF 檔名）、`bank_code`（銀行代碼）、`error_type`（錯誤類型）、`error_detail`（錯誤詳情）

#### Scenario: Parse 失敗記錄缺失欄位

- **WHEN** parse 因必要欄位缺失而失敗（`ParseError`）
- **THEN** 日誌 SHALL 額外包含 `missing_fields` 欄位，列出所有缺失的欄位名稱

#### Scenario: 非預期錯誤記錄完整 traceback

- **WHEN** parse 因非預期例外失敗（非 `ParseError`）
- **THEN** 日誌 SHALL 包含完整 traceback（`exc_info=True`）

### Requirement: Parser 選擇過程 logging

系統 SHALL 在 parser registry 解析附件時記錄選擇過程，包括嘗試了哪些 parser、結果如何。

#### Scenario: 記錄 parser 嘗試順序

- **WHEN** registry 為某個附件解析 parser 候選列表
- **THEN** 系統 SHALL 以 DEBUG 等級記錄每個被嘗試的 parser 名稱與 `can_parse()` 結果

#### Scenario: 記錄最終匹配的 parser

- **WHEN** 某個 parser 的 `can_parse()` 回傳 True 且被選用
- **THEN** 系統 SHALL 以 INFO 等級記錄：`parser_name`、`parser_version`、`bank_code`、`pdf_filename`

#### Scenario: 所有 parser 均無法匹配

- **WHEN** 所有候選 parser 的 `can_parse()` 均回傳 False
- **THEN** 系統 SHALL 以 WARNING 等級記錄：`pdf_filename`、所有嘗試過的 parser 名稱列表
