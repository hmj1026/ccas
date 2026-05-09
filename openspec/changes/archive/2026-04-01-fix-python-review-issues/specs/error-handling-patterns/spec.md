## MODIFIED Requirements

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
