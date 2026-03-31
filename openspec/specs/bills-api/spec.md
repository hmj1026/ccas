# bills-api Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
### Requirement: 提供帳單列表 API
系統 SHALL 提供 `GET /api/bills`，支援 `month` 與 `status=all|paid|unpaid` 查詢參數；若未提供 `month`，預設為當月，若未提供 `status`，預設為 `all`。

#### Scenario: 查詢當月全部帳單
- **WHEN** 前端呼叫 `GET /api/bills`
- **THEN** API 會回傳當月所有帳單資料

#### Scenario: 查詢當月未繳帳單
- **WHEN** 前端呼叫 `GET /api/bills?status=unpaid`
- **THEN** API 只回傳當月 `is_paid=false` 的帳單

### Requirement: 帳單列表回應包含 PDF 下載連結
系統 SHALL 在帳單列表的每筆回應中包含 PDF 下載 URL，讓前端可直接連結到原始帳單 PDF。

#### Scenario: 帳單回應包含 pdf_url
- **WHEN** 前端呼叫 `GET /api/bills` 且帳單有對應的 staged PDF
- **THEN** 每筆帳單資料中會包含 `pdf_url` 欄位，指向 `/api/bills/{bill_id}/pdf`

#### Scenario: 無 PDF 時 pdf_url 為 null
- **WHEN** 某筆帳單沒有對應的 staged PDF（例如手動建立的帳單）
- **THEN** 該帳單的 `pdf_url` 欄位為 `null`

### Requirement: 提供帳單原始 PDF 下載端點
系統 SHALL 提供 `GET /api/bills/{bill_id}/pdf`，回傳該帳單對應的原始 PDF 檔案 binary。

#### Scenario: 成功下載帳單 PDF
- **WHEN** 前端呼叫 `GET /api/bills/123/pdf` 且該帳單有對應的 staged PDF
- **THEN** API 會回傳 PDF binary，Content-Type 為 `application/pdf`

#### Scenario: 帳單存在但 PDF 檔案遺失
- **WHEN** 前端呼叫 `GET /api/bills/123/pdf` 但 staging 目錄中找不到對應檔案
- **THEN** API 回傳 404 並說明 PDF 檔案不存在

### Requirement: 提供帳單付款狀態更新 API
系統 SHALL 提供 `PATCH /api/bills/{bill_id}`，允許前端更新帳單的 `is_paid` 狀態。

#### Scenario: 將帳單標記為已繳
- **WHEN** 前端送出 `PATCH /api/bills/123` 並帶入 `{"is_paid": true}`
- **THEN** API 會更新該帳單狀態並回傳最新資料

