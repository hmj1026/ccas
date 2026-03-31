## 背景 (Context)

在 backend API、parser、classifier 完成後，系統將具備足夠資料供前端呈現。Dashboard 的責任是把這些資料轉成可搜尋、可分析、可管理的 UI，並與 Telegram 作為不同層級的使用介面互補。這個 change 需要明確定義各頁面責任、路由、資料抓取模式與互動邏輯。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 提供與產品規格一致的五個主要頁面
- 讓使用者可從 UI 檢視總覽、交易、分析圖表、帳單與設定
- 讓篩選、分頁與匯出行為與 backend API 對齊
- 讓頁面在桌機與手機尺寸上都可使用

**非目標：**
- 不在此 change 中重新定義 backend API
- 不處理多使用者登入或權限管理
- 不做高度客製的資料編輯器或拖拉式圖表 builder

## 決策 (Decisions)

### D1: 採用 route-based SPA 結構

**選擇**: 前端使用 client-side routing，將 `/overview`、`/transactions`、`/analytics`、`/bills`、`/settings` 作為主要路由，根路徑 `/` 導向 `/overview`。

**理由**: 每個頁面責任清楚，易於分享連結與保留頁面狀態。

**考慮過的替代方案**:
- 單頁籤式大頁面：狀態過於集中，不易維護

### D2: 資料抓取與快取交由查詢層管理

**選擇**: 前端透過查詢層集中處理 API 請求、loading、error 與 refetch 行為。

**理由**: Dashboard 會有大量列表與圖表資料，集中處理資料狀態能減少重複邏輯。

**考慮過的替代方案**:
- 在元件內直接手寫 fetch：重複邏輯多，維護差

### D3: 交易與帳單頁的篩選條件同步到 URL query params

**選擇**: Transactions 與 Bills 頁面的主要 filter 狀態同步到 URL query params。

**理由**: 使用者可保留與分享特定篩選條件，也更利於重新整理後還原狀態。

**考慮過的替代方案**:
- 只存在 local state：重新整理就遺失

### D4: 圖表頁使用後端聚合資料，前端只負責呈現

**選擇**: Analytics 頁直接使用 backend API 回傳的聚合結果繪圖，不在前端自行彙總全部交易。

**理由**: 可避免前端負責過多資料計算，保持頁面簡潔。

**考慮過的替代方案**:
- 前端拿 raw data 自己算：會增加資料量與邏輯負擔

### D5: Mutation 先採「提交後 refetch」，不做 optimistic update

**選擇**: Bills 與 Settings 頁面的修改先採送出成功後重新抓取資料的模式。

**理由**: 初期互動量不高，這種模式較簡單且行為穩定。

**考慮過的替代方案**:
- optimistic update：互動更即時，但狀態處理較複雜

## 風險 / 取捨 (Risks / Trade-offs)

**頁面多且資料來源分散** → 以頁面責任與 API 對應來約束 scope  
**圖表在小螢幕上可讀性差** → 要求 responsive layout 與簡潔 legend  
**篩選狀態複雜** → 透過 query params 固定化主要篩選欄位
