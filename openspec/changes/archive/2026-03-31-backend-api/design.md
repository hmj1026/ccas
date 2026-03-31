## 背景 (Context)

前端 dashboard 需要 Overview、Transactions、Analytics、Bills、Settings 五個頁面的資料，而 Telegram Bot 以外的其他整合也適合透過 HTTP API 存取。這個 change 的目標是把資料查詢與更新需求整理成清楚、穩定且可測試的 REST 介面。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 提供對齊 dashboard 頁面需求的 REST API
- 讓交易查詢支援常用篩選、搜尋、分頁與 CSV 匯出
- 提供圖表所需的聚合資料，而非讓前端自行彙總大量 raw data
- 讓帳單付款狀態與設定內容可被 dashboard 更新

**非目標：**
- 不在此 change 中實作前端頁面
- 不處理非 HTTP 的外部整合協議
- 不提供複雜授權模型，先以單使用者本地工具為前提

## 決策 (Decisions)

### D1: 所有業務 API 都放在 `/api` 命名空間下

**選擇**: 路由統一使用 `/api/...` 前綴。

**理由**: 和既有 `/health` 區隔清楚，也方便前端 proxy 與後續版本化。

**考慮過的替代方案**:
- 將所有路由直接掛在根路徑：不利區分健康檢查與業務 API

### D2: 月份查詢統一使用 `YYYY-MM`

**選擇**: 涉及月份的 API 一律使用 `YYYY-MM` 字串作為月份參數格式；若該 API 的月份參數省略，預設為當月。

**理由**: 這與資料模型 `billing_month` 一致，也能簡化前後端對齊。

**考慮過的替代方案**:
- 使用日期區間：彈性較大，但對目前需求過重

### D3: 交易列表採分頁，CSV 匯出共用相同過濾條件

**選擇**: `GET /api/transactions` 提供分頁 JSON 結果；`GET /api/transactions/export` 使用同一組 filter 輸出 CSV。

**理由**: 正常瀏覽與匯出是兩種不同使用情境，但應共享一套查詢語意，避免結果不一致。

**考慮過的替代方案**:
- 讓前端自行把全部 JSON 轉 CSV：在資料量大時不理想

### D4: 聚合資料由後端提供

**選擇**: 類別分布、銀行比較與月趨勢都由後端直接回傳已聚合結果。

**理由**: 這可減少前端重複實作彙總邏輯，也避免傳輸過多 raw transactions。

**考慮過的替代方案**:
- 前端拿全部交易自行彙總：資料量變大時效能較差

### D5: Settings API 直接暴露 `bank_configs` 與 `categories` 的 CRUD

**選擇**: v1 直接提供銀行設定與分類關鍵字的 CRUD 路由，包含 `is_active`。

**理由**: 這正對應產品規格中的 Settings 頁面需求，也方便 Gmail 與 parser 的設定維護。

**考慮過的替代方案**:
- 只提供唯讀 API：後續仍需額外補 mutation 介面

### D6: 提供帳單 PDF 原始檔案的存取端點

**選擇**: 新增 `GET /api/bills/{bill_id}/pdf` 端點，從 staging 目錄讀取對應的原始 PDF 檔案並回傳 binary response。

**理由**: Dashboard 的帳單頁面需要讓使用者可以檢視或下載原始帳單 PDF。PDF 檔案已由 gmail-ingestor 落地到 staging 目錄並記錄路徑，後端只需提供安全的檔案存取即可。

**考慮過的替代方案**:
- 前端直接存取檔案系統：不安全，且在 Docker 環境中不可行
- 使用獨立檔案服務（如 S3）：對個人工具架構過重

### D7: 所有 `/api` 端點加入 Bearer Token 驗證

**選擇**: 在 `/api` 命名空間下的所有端點加入 Bearer Token 驗證 middleware。Token 值從環境變數 `API_TOKEN` 讀取，未通過驗證的請求回傳 401。

**理由**: 雖然是個人工具，但部署到 server 後 API 不應完全裸露。Bearer Token 是最簡單的保護機制，不需要使用者資料庫或 session 管理。

**考慮過的替代方案**:
- 不加任何認證：部署到網路後有安全風險
- OAuth / JWT：對單使用者工具過於複雜
- IP 白名單：不適用於行動裝置存取

## 風險 / 取捨 (Risks / Trade-offs)

**API 數量較多** → 以頁面需求切分，避免單一萬用 endpoint 過大
**CSV 匯出與列表查詢條件不一致的風險** → 明確要求共用相同 filter 契約
**Settings mutation 會直接影響 ingestion / parser 行為** → 先由 schema 驗證與測試保護輸入
**PDF 檔案存取需防止路徑穿越攻擊** → 只允許透過 bill_id 查詢對應的 staging 路徑，不接受任意檔案路徑
**Bearer Token 遺失或洩漏** → Token 從環境變數讀取，不寫入程式碼；可隨時更換
