## ADDED Requirements

### Requirement: 以 mocked 外部服務執行完整 pipeline 的端對端測試
系統 SHALL 提供端對端測試套件，使用 mocked Gmail API 與 mocked Telegram API，搭配真實 in-memory SQLite 資料庫與真實 pipeline 執行路徑，驗證從帳單抓取到通知送出的完整流程。

#### Scenario: 成功路徑完整流程通過驗證
- **WHEN** mocked Gmail API 回傳包含 PDF 附件的候選郵件，且所有後續處理步驟均成功
- **THEN** E2E 測試應通過，並可斷言 `bills` 與 `transactions` 記錄已正確建立，且 mocked Telegram API 收到通知呼叫

#### Scenario: E2E 測試不依賴真實外部服務
- **WHEN** 在無網路連線或無 Gmail 帳號憑證的環境中執行 E2E 測試
- **THEN** 測試應仍能正常啟動並完成，不因外部服務不可用而失敗

### Requirement: 驗證 staging 狀態機的完整生命週期
系統 SHALL 以獨立測試案例驗證 staging record 在完整生命週期中的每一個狀態轉換，包含成功路徑與所有已定義的錯誤分支。

#### Scenario: 成功路徑狀態轉換序列
- **WHEN** 附件成功完成 ingest、decrypt、parse 三個階段
- **THEN** staging record 的 `status` 應依序從 `staged` 轉換至 `decrypted`，再轉換至 `parsed`

#### Scenario: 解密失敗的錯誤分支
- **WHEN** 附件在 decrypt 階段發生失敗
- **THEN** staging record 的 `status` 應更新為 `decrypt_failed`，且 `error_reason` 欄位應保存失敗原因

#### Scenario: 解析失敗的錯誤分支
- **WHEN** 附件在 parse 階段發生失敗
- **THEN** staging record 的 `status` 應更新為 `parse_failed`，且 `error_reason` 欄位應保存失敗原因

### Requirement: 單筆失敗不中斷同批次其他項目的處理
系統 SHALL 確保當批次中某一項目進入錯誤狀態時，同批次其餘項目的後續處理流程不受中斷。

#### Scenario: 解密失敗不中斷其餘附件的解析
- **WHEN** 批次中有一個附件 `status = decrypt_failed`，同時有其他附件 `status = staged`
- **THEN** 其他附件仍應繼續進入解析流程，最終產出對應的 `bills` 與 `transactions` 記錄

#### Scenario: 通知失敗不中斷整體 pipeline
- **WHEN** Telegram 通知呼叫拋出例外
- **THEN** pipeline 應記錄錯誤至日誌，並繼續完成當次執行，不向上拋出未捕捉的例外
