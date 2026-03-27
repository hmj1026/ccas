## 緣由 (Why)

CCAS 的最終產品不只需要資料收集與推播，還需要一個可視化介面讓使用者檢視消費趨勢、篩選交易、管理帳單與調整設定。產品規格已明確定義 Overview、Transactions、Analytics、Bills、Settings 五個頁面，因此需要一個獨立的 dashboard change 來把這些頁面行為正式規格化。

## 變更內容 (What Changes)

- 新增 Overview 頁面，顯示本月總覽、繳費狀態卡片與即將到期帳單
- 新增 Transactions 頁面，支援搜尋、篩選、分頁與 CSV 匯出
- 新增 Analytics 頁面，顯示月趨勢、類別分布與銀行比較圖表
- 新增 Bills 頁面，支援帳單列表、付款狀態切換與 PDF 連結
- 新增 Settings 頁面，支援銀行設定與分類關鍵字管理

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)
- `overview-page`: 本月總覽與即將到期帳單頁面
- `transactions-page`: 交易查詢、篩選與匯出頁面
- `analytics-page`: 趨勢與分布圖表頁面
- `bills-page`: 帳單列表與付款狀態管理頁面
- `settings-page`: 銀行設定與分類規則管理頁面

### 修改能力 (Modified Capabilities)
(無 -- 沒有既有 capability 的 requirement 被修改)

## 影響範圍 (Impact)

- **前端模組**: `pages/`、`components/`、`api/`、`types/`
- **前端依賴**: 需要 client-side routing、資料抓取與圖表顯示能力
- **使用者體驗**: 提供完整視覺化管理介面，對應所有主要產品場景
