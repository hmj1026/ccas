## 1. 解密服務核心

- [x] 1.1 新增 `pikepdf` 相依套件並確認可正常匯入
- [x] 1.2 實作從 `bank_configs.pdf_password_rule` 解析密碼規則並產生密碼的邏輯
- [x] 1.3 實作 PDF 解密函式，使用 `pikepdf` 嘗試以產生的密碼開啟並輸出解密後的 PDF
- [x] 1.4 實作未加密 PDF 的偵測與透通邏輯（`pikepdf` 無需密碼即可開啟視為透通）
- [x] 1.5 確保解密後的 PDF 覆寫原始 staging 路徑（in-place），不產生額外副本

## 2. Staging 整合

- [x] 2.1 實作查詢 staging 中狀態為可解密（例如 `staged`）之附件的資料存取層
- [x] 2.2 實作解密成功後將 staging status 更新為 `decrypted` 的邏輯
- [x] 2.3 實作解密失敗後將 staging status 更新為 `decrypt_failed` 並寫入 `error_reason` 的邏輯
- [x] 2.4 確保已為 `decrypted` 狀態的附件在重跑時被略過（idempotent 保護）

## 3. 批次解密 Job

- [x] 3.1 實作批次解密 job 入口，依序處理所有等待解密的附件
- [x] 3.2 確保單筆附件解密失敗不中止整個批次，並記錄失敗原因
- [x] 3.3 實作包含成功、略過與失敗統計的 batch summary 輸出

## 4. 測試覆蓋

- [x] 4.1 新增密碼規則解析與密碼產生的單元測試，涵蓋各種規則格式
- [x] 4.2 新增加密 PDF 以正確密碼解密成功的單元測試
- [x] 4.3 新增加密 PDF 以錯誤密碼解密失敗的單元測試，驗證 `decrypt_failed` 狀態與 `error_reason` 寫入
- [x] 4.4 新增未加密 PDF 透通的單元測試，驗證不拋出例外且狀態更新為 `decrypted`
- [x] 4.5 新增 idempotent 保護的單元測試，驗證已 `decrypted` 的附件不會被重複處理
- [x] 4.6 新增批次 job 的整合測試，涵蓋多附件混合情境（成功、透通、失敗）與 batch summary 輸出
