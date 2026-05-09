## 1. API 基礎結構

- [x] 1.1 建立 API router 與 schema 組織方式
- [x] 1.2 建立共用月份、分頁與錯誤回應驗證規則
- [x] 1.3 實作 Bearer Token 認證 middleware，從環境變數 `API_TOKEN` 讀取，未通過驗證回傳 401
- [x] 1.4 將認證 middleware 套用到所有 `/api` 路由（`/health` 除外）

## 2. 查詢與報表 API

- [x] 2.1 實作 `GET /api/overview`
- [x] 2.2 實作 `GET /api/transactions` 與 `GET /api/transactions/export`
- [x] 2.3 實作 `GET /api/analytics/trend`、`GET /api/analytics/categories`、`GET /api/analytics/banks`

## 3. 帳單與設定 API

- [x] 3.1 實作 `GET /api/bills` 與 `PATCH /api/bills/{bill_id}`
- [x] 3.1.1 實作 `GET /api/bills/{bill_id}/pdf` 帳單原始 PDF 下載端點，含路徑穿越防護
- [x] 3.2 實作 `GET/POST/PATCH` 的銀行設定 API
- [x] 3.3 實作 `GET/POST/PATCH/DELETE` 的分類關鍵字 API

## 4. 測試覆蓋

- [x] 4.1 新增 overview、transactions 與 analytics 路由測試
- [x] 4.2 新增帳單狀態更新與設定 CRUD 測試
- [x] 4.3 新增 CSV 匯出與參數驗證測試
- [x] 4.4 新增 Bearer Token 認證 middleware 測試（有效/無效/缺少 token）
- [x] 4.5 新增 PDF 下載端點測試（正常下載、bill 不存在、PDF 檔案遺失）
