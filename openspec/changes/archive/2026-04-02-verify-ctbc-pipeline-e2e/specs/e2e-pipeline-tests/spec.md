## MODIFIED Requirements

### Requirement: 以 mocked 外部服務執行完整 pipeline 的端對端測試
系統 SHALL 提供端對端測試套件，使用 mocked Gmail API 與 mocked Telegram API，搭配真實 in-memory SQLite 資料庫與真實 pipeline 執行路徑，驗證從帳單抓取到通知送出的完整流程。

#### Scenario: 成功路徑完整流程通過驗證
- **WHEN** mocked Gmail API 回傳包含 PDF 附件的候選郵件，且所有後續處理步驟均成功
- **THEN** E2E 測試應通過，並可斷言 `bills` 與 `transactions` 記錄已正確建立，且 mocked Telegram API 收到通知呼叫

#### Scenario: E2E 測試不依賴真實外部服務
- **WHEN** 在無網路連線或無 Gmail 帳號憑證的環境中執行 E2E 測試
- **THEN** 測試應仍能正常啟動並完成，不因外部服務不可用而失敗

#### Scenario: 去重複機制在 E2E 測試中可驗證
- **WHEN** E2E 測試執行兩次 pipeline（第二次不帶 force）且第一次已成功 ingest 相同附件
- **THEN** 第二次執行的 ingest 階段 `skipped_count` SHALL 大於 0，parse 階段 `skipped_count` SHALL 大於 0，且 DB 中不產生重複的 Bill 記錄
