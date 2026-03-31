## 緣由 (Why)

`gmail-ingestor` 已能將帳單 PDF 落地到 staging 區，但許多銀行會以密碼保護其 PDF 帳單（常見規則如「身分證後 4 碼 + 生日 MMDD」）。若直接將加密 PDF 傳入 parser engine，parser 無法開啟檔案，必然解析失敗。因此在 parser engine 之前需要一個獨立的解密步驟，確保後續 parser 收到的都是可讀取的 PDF。

## 變更內容 (What Changes)

- 新增 PDF 解密能力，使用 `pikepdf` 依 `bank_configs.pdf_password_rule` 為每家銀行產生密碼並嘗試解密
- 新增對未加密 PDF 的透通處理，讓無需解密的附件也能無縫進入後續流程
- 新增解密狀態追蹤，在 staging record 上標記 `decrypted` 或 `decrypt_failed` 並保存錯誤原因
- 定義可由排程或 pipeline 呼叫的批次解密 job 入口，供後續 `parser-engine` 與 `pipeline-scheduler` 串接

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `pdf-decryption`: 依銀行密碼規則將加密 PDF 解密，未加密 PDF 透通，並以 staging 狀態追蹤每筆附件的解密結果

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `decryptor/`、`storage/`
- **資料模型語意**: staging attachment 的 `decrypted` / `decrypt_failed` 狀態轉換，以及 `error_reason` 欄位寫入
- **依賴 change**: `foundation-setup`（基礎架構）、`gmail-ingestor`（staging 資料表與待解密附件）
- **作業流程**: 填補 Gmail ingestion 與 parser engine 之間的解密缺口，讓整條 pipeline 可以端到端運作
