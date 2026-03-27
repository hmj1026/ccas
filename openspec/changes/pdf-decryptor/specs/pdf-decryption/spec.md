## ADDED Requirements

### Requirement: 依銀行密碼規則解密加密 PDF
系統 SHALL 從 `bank_configs.pdf_password_rule` 取得每家銀行的密碼產生規則，並以產生的密碼嘗試解密該銀行的 staged PDF。

#### Scenario: 以正確密碼解密加密 PDF
- **WHEN** 某個 staged PDF 為加密狀態，且系統依 `pdf_password_rule` 產生的密碼正確
- **THEN** 系統會以解密後的內容覆寫原始 staging 路徑，並將該附件的 staging status 更新為 `decrypted`

#### Scenario: 密碼錯誤時標記為 `decrypt_failed`
- **WHEN** 某個 staged PDF 為加密狀態，但系統產生的密碼無法開啟該檔案
- **THEN** 系統會將該附件的 staging status 更新為 `decrypt_failed`，並保存描述失敗原因的 error reason

### Requirement: 未加密 PDF 直接透通
系統 SHALL 在偵測到 PDF 本身不需要密碼時，直接將其視為可讀取並更新狀態，不拋出例外或標記失敗。

#### Scenario: 未加密 PDF 透通並標記為 `decrypted`
- **WHEN** 某個 staged PDF 本身不需要密碼即可開啟
- **THEN** 系統不會嘗試套用密碼規則，直接將該附件的 staging status 更新為 `decrypted`，讓後續 parser 可以接手

#### Scenario: 未設定密碼規則的銀行也能透通
- **WHEN** 某家銀行的 `pdf_password_rule` 為空或未設定，且其 PDF 附件本身不加密
- **THEN** 系統仍可正常將該附件標記為 `decrypted`，不視為設定缺漏錯誤

### Requirement: 解密冪等性保護
系統 SHALL 在批次重跑時略過已標記為 `decrypted` 的附件，避免重複覆寫已解密的檔案。

#### Scenario: 重跑時略過已解密附件
- **WHEN** 批次解密 job 再次遇到 staging status 已為 `decrypted` 的附件
- **THEN** 系統不會再次執行解密流程，並在 batch summary 中將其標記為略過

### Requirement: 批次解密容錯不中止
系統 SHALL 在單筆附件解密失敗時繼續處理其餘附件，並回傳包含成功、略過與失敗統計的 batch summary。

#### Scenario: 單筆失敗不中止整批
- **WHEN** 批次解密 job 處理多個附件，其中某一筆因密碼錯誤或 pikepdf 例外而失敗
- **THEN** 系統記錄該筆的 `decrypt_failed` 狀態與 error reason，並繼續處理剩餘附件，最終回傳完整的 batch summary
