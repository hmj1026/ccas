## 背景 (Context)

在 `foundation-setup` 與 `gmail-ingestor` 之後，系統已具備基礎架構與 Gmail 附件 staging 能力。然而台灣常見銀行（如國泰世華、中信、玉山）的帳單 PDF 均設有密碼保護，密碼通常為個人識別資訊的組合（例如「身分證後 4 碼 + 生日 MMDD」），各家銀行規則不同。若未先解密，`pikepdf` 或任何 PDF parser 都無法讀取檔案內容。

本 change 的範圍集中在解密步驟本身，不處理 Gmail 搜尋、下載或 PDF 內容解析。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 從 `bank_configs.pdf_password_rule` 取得每家銀行的密碼產生規則，並動態計算密碼
- 使用 `pikepdf` 嘗試解密 staging 區中的加密 PDF
- 對未加密 PDF 直接透通，不視為錯誤
- 以 staging 狀態（`decrypted` / `decrypt_failed`）追蹤每個附件的解密結果
- 定義批次解密 job 入口，讓後續 pipeline 可以串接

**非目標：**
- 不處理 Gmail 搜尋與附件下載
- 不解析 PDF 內容（帳單、交易明細）
- 不提供前端頁面或 API route
- 不管理密碼以外的使用者個資

## 決策 (Decisions)

### D1: 密碼規則完全來自 `bank_configs.pdf_password_rule`

**選擇**: 每家銀行的 PDF 密碼由 `bank_configs.pdf_password_rule` 欄位描述，解密服務依此規則動態產生密碼，不在程式碼中硬編碼任何銀行專屬邏輯。

**理由**: 密碼規則屬於銀行差異最大的部分，放在設定層可讓每家銀行獨立維護，符合後續 Settings / Dashboard 管理方向，也避免每次增加銀行都需修改程式碼。

**考慮過的替代方案**:
- 在程式內依 `bank_code` 硬編碼各家密碼邏輯：擴充性差，每次新增銀行都需改程式碼
- 將密碼規則放在 YAML 設定檔：可行，但會與既有 `bank_configs` 資料表職責重疊

### D2: 解密後覆寫原始 staging 路徑，不產生額外副本

**選擇**: 解密成功後，以解密後的 PDF 覆寫原始 staging 路徑（in-place），不在 staging 目錄外建立額外副本。

**理由**: 後續 parser 只需知道 staging path 即可接手，不需感知「加密版」與「解密版」的路徑差異。覆寫原始檔可避免檔案增生，也讓 staging record 的 `file_path` 欄位保持單一且穩定。

**考慮過的替代方案**:
- 將解密後的 PDF 另存到新路徑，保留原始加密檔：增加檔案數量，staging record 需多一欄追蹤解密路徑，後續 parser 需感知兩條路徑
- 刪除加密原檔，只保留解密版：效果同覆寫，但多一個刪除步驟，邏輯較複雜

### D3: 未加密 PDF 直接透通，不視為錯誤

**選擇**: 使用 `pikepdf` 開啟 PDF 時，若檔案本身不需要密碼，直接將其視為「已可讀取」並更新狀態為 `decrypted`，不拋出例外或標記失敗。

**理由**: 部分銀行的帳單 PDF 不加密，強制要求所有附件都必須有密碼規則會造成不必要的設定負擔。`pikepdf` 可直接偵測是否需要密碼，透通邏輯可由 library 本身提供，不需額外實作。

**考慮過的替代方案**:
- 只允許明確設定了 `pdf_password_rule` 的銀行才能執行解密流程，否則 skip：會使未加密銀行的附件永遠停在 `staged` 狀態，無法繼續進入 parser
- 對未加密 PDF 標記為特殊 `no_encryption` 狀態：引入額外狀態值，增加下游流程判斷複雜度

### D4: 以 staging 狀態追蹤解密結果，不新增獨立資料表

**選擇**: 解密成功後更新 staging record 的 status 為 `decrypted`；解密失敗後更新為 `decrypt_failed` 並寫入 `error_reason`；已為 `decrypted` 的附件在重跑時略過。

**理由**: Staging record 本已代表附件的完整生命週期，在同一筆記錄上追加解密狀態最符合現有資料模型。不需要額外資料表，parser 只需過濾 `status = decrypted` 的附件即可接手，不需感知解密流程細節。

**考慮過的替代方案**:
- 新增獨立的 `decryption_results` 資料表：資料重複，staging record 與解密結果需 join 才能完整呈現一個附件的狀態，維護成本較高
- 僅以 log 記錄解密結果：無法穩定查詢已解密或失敗的附件，無法作為後續流程的觸發條件

## 風險 / 取捨 (Risks / Trade-offs)

**密碼規則錯誤或使用者個資有誤** → 解密嘗試失敗，staging 狀態更新為 `decrypt_failed` 並記錄明確錯誤訊息，不中止其他附件的處理
**銀行更換密碼規則** → 只需更新 `bank_configs.pdf_password_rule`，程式碼不需修改
**`pikepdf` 無法解開某些加密演算法** → 標記為 `decrypt_failed`，等待人工補救或升級 pikepdf 版本
**覆寫原始加密檔後無法回溯** → 原始加密檔來源為 Gmail，必要時可重新從 Gmail 下載；加密與解密版本內容完全相同，僅差在是否可讀取
**批次中單筆解密失敗** → 記錄失敗原因並繼續處理其餘附件，確保批次容錯不中止
