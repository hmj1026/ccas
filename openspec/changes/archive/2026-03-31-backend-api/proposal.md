## 緣由 (Why)

React Dashboard 與部分自動化流程需要透過穩定的 HTTP 介面讀寫帳單、交易、分析資料與設定內容。目前系統只有基礎的 `/health`，尚未定義真正的業務 API，因此需要建立一個對齊 dashboard 頁面需求的 backend API change。

## 變更內容 (What Changes)

- 新增 Overview API，提供本月摘要卡片與即將到期帳單
- 新增 Transactions API，支援篩選、搜尋、分頁與 CSV 匯出
- 新增 Analytics API，提供月趨勢、類別分布與銀行比較
- 新增 Bills API，支援帳單列表與付款狀態更新
- 新增 Settings API，支援銀行設定與分類關鍵字管理

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `overview-api`: 提供 dashboard 首頁摘要資料
- `transactions-api`: 提供交易查詢、篩選、分頁與 CSV 匯出
- `analytics-api`: 提供報表圖表需要的聚合資料
- `bills-api`: 提供帳單列表查詢與付款狀態更新
- `settings-api`: 提供 `bank_configs` 與 `categories` 的管理接口

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **後端模組**: `api/`、`storage/`
- **資料存取**: 會讀寫 `bills`、`transactions`、`categories`、`bank_configs`
- **前端依賴**: dashboard 各頁面將以這些 API 作為單一資料來源
