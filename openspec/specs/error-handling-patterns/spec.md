# error-handling-patterns Specification

## Purpose
TBD - created by archiving change integration-polish. Update Purpose after archive.
## Requirements
### Requirement: 共用例外階層以 `CcasError` 為基底

系統 SHALL 維持以 `CcasError` 為基底的共用例外階層，且 attachment ingestion、parser 探測與 RQ failure handling MUST 僅捕捉預期的 domain、PDF 與 I/O 例外；對已處理失敗 SHALL 記錄 traceback，未預期例外 SHALL 持續向上傳播。

#### ADDED Scenario: ingestor attachment 處理僅捕捉預期例外
- **WHEN** `_process_attachment` 執行附件下載與寫檔
- **THEN** 僅捕捉 `IngestError` 和 `OSError`，其他未預期例外向上傳播
- **AND** 捕捉時記錄完整 traceback（`exc_info=True`）

#### ADDED Scenario: parser can_parse 僅捕捉 PDF 讀取例外
- **WHEN** `can_parse` 嘗試開啟並辨識 PDF
- **THEN** 僅捕捉 PDF 解析相關例外（`pdfplumber.exceptions` 和 `OSError`），其他未預期例外向上傳播

#### ADDED Scenario: RQ failure handler 不吞掉內部例外
- **WHEN** `on_failure_handler` 執行 manual review 標記時發生錯誤
- **THEN** 該錯誤會被記錄（含 traceback），不會覆蓋原始 pipeline 失敗資訊

### Requirement: 結構化日誌輸出 JSON 格式
系統 SHALL 使用 Python stdlib `logging` 模組搭配自訂 `JsonFormatter`，輸出包含必要欄位的 JSON 格式日誌，以利後續接入 log aggregation 工具。

#### Scenario: 日誌記錄包含必要的結構化欄位
- **WHEN** 任何模組透過 `logging.getLogger(__name__)` 輸出日誌
- **THEN** 每一條日誌記錄應為合法的 JSON 物件，包含 `timestamp`、`level`、`logger`、`message` 欄位

#### Scenario: 各模組使用模組層級 logger
- **WHEN** 某模組呼叫 `logging.getLogger(__name__)`
- **THEN** 日誌記錄的 `logger` 欄位應反映該模組的完整路徑（例如 `ingestor.service`）

### Requirement: 日誌輸出不包含機敏資訊
系統 SHALL 在所有日誌輸出進入 handler 之前，自動遮罩符合機敏模式的欄位值，確保 OAuth token、密碼與 credentials 路徑不會出現在日誌記錄中。

#### Scenario: OAuth token 值在日誌中被遮罩
- **WHEN** 日誌訊息中包含 OAuth access token 或 refresh token 的實際值
- **THEN** 輸出的日誌記錄應將該值替換為 `[REDACTED]`，不顯示原始 token

#### Scenario: 密碼與 credentials 路徑在日誌中被遮罩
- **WHEN** 日誌訊息中包含密碼欄位值或本地 credentials 檔案完整路徑
- **THEN** 輸出的日誌記錄應將對應值替換為 `[REDACTED]`

#### Scenario: 不含機敏資訊的日誌正常輸出
- **WHEN** 日誌訊息不包含任何已定義的機敏模式
- **THEN** 訊息內容應保持原樣，不被遮罩修改

### Requirement: 日誌等級與格式可透過 Settings 設定
系統 SHALL 從 `Settings` 讀取 `log_level` 與 `log_format` 欄位，並在應用程式啟動時套用至 root logger，確保日誌行為可在不修改程式碼的情況下調整。

#### Scenario: 從 Settings 套用指定的日誌等級
- **WHEN** `Settings.log_level` 設為 `"DEBUG"`
- **THEN** DEBUG 等級及以上的日誌記錄均應輸出，不被過濾

#### Scenario: 使用預設值確保安全啟動
- **WHEN** `Settings` 中未明確設定 `log_level` 或 `log_format`
- **THEN** 系統應以 `"INFO"` 等級與 `"json"` 格式作為預設值正常啟動

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

