## 緣由 (Why)

Parser 只會把帳單轉成原始交易資料，但報表、分析與 Telegram 摘要需要可用的消費分類。CCAS 的產品方向明確採用關鍵字規則分類，因此需要一個可維護、可重跑、行為可預期的 keyword classifier change。

## 變更內容 (What Changes)

- 新增以 `categories` 資料表為來源的分類規則載入機制
- 新增根據商家名稱判斷消費類別的關鍵字分類引擎
- 新增預設未分類處理與 deterministic 比對規則
- 新增將分類結果套用到 `Transaction.category` 的流程
- 新增可對既有交易重跑分類的能力，供後續設定調整使用

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `keyword-mapping-source`: 從 `categories` 資料表載入分類關鍵字映射
- `classification-engine`: 以固定規則將商家名稱對應到分類
- `classification-application`: 將分類結果套用到交易資料，並支援重跑

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `classifier/`、`storage/`
- **資料欄位**: `Transaction.category` 的填值流程
- **後續功能**: Telegram 摘要、分析圖表與分類維護 UI 都可直接依賴分類結果
