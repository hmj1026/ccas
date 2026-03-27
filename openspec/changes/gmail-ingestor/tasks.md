## 1. Gmail 整合契約

- [ ] 1.1 建立 Gmail ingestion service 的介面，涵蓋驗證、郵件搜尋與附件下載
- [ ] 1.2 補齊載入 Gmail credentials 與 token path 所需的設定欄位或 helper
- [ ] 1.3 定義讀取啟用中且具 `gmail_filter` 的銀行設定查詢方式
- [ ] 1.4 實作 OAuth token 自動刷新機制（google-auth `Credentials.refresh()`），refresh 失敗時記錄明確錯誤與重新授權指引
- [ ] 1.5 實作 Gmail API 呼叫的 exponential backoff retry（最多 3 次，1s/2s/4s），針對 429 與 5xx 狀態碼

## 2. 附件 Staging

- [ ] 2.1 新增下載 Gmail 附件所需的 staging 資料模型與 migration
- [ ] 2.2 實作 PDF 附件的可預期 staging path 產生規則
- [ ] 2.3 實作以 Gmail message 與 attachment identity 為基礎的 dedupe 規則
- [ ] 2.4 為成功與失敗的附件處理都保存 staging status 與 error reason

## 3. Ingestion Job 流程

- [ ] 3.1 實作單次 ingestion job 入口，逐一處理啟用中的銀行設定
- [ ] 3.2 實作僅接受 PDF 的附件過濾與逐附件處理流程
- [ ] 3.3 實作包含成功、略過與失敗統計的 batch summary 輸出
- [ ] 3.4 確保單筆失敗會被記錄，但不會中止整個 batch

## 4. 測試覆蓋

- [ ] 4.1 新增 Gmail 查詢組裝與啟用銀行選擇的單元測試
- [ ] 4.2 新增 PDF 附件過濾、staging path 與 dedupe 行為的單元測試
- [ ] 4.3 使用 mocked Gmail API 回應新增整合測試，覆蓋成功下載與失敗處理
- [ ] 4.4 新增 job-level 測試，驗證多銀行處理與 batch summary 輸出
- [ ] 4.5 新增 OAuth token 刷新與刷新失敗的單元測試
- [ ] 4.6 新增 Gmail API retry 行為的單元測試（429/5xx 重試、非暫時性錯誤不重試）
