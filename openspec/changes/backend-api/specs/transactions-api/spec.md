## ADDED Requirements

### Requirement: 提供交易查詢 API
系統 SHALL 提供 `GET /api/transactions`，支援 `month`、`bank_code`、`category`、`q`、`page`、`page_size`、`sort` 等查詢參數，並回傳分頁結果。

#### Scenario: 以月份與分類過濾交易
- **WHEN** 前端呼叫 `GET /api/transactions?month=2026-03&category=餐飲`
- **THEN** API 只回傳符合該月份與分類條件的交易結果

#### Scenario: 回傳分頁資料
- **WHEN** 前端呼叫 `GET /api/transactions?page=2&page_size=50`
- **THEN** API 會回傳第 2 頁資料，並包含分頁所需的總筆數與頁碼資訊

### Requirement: 提供交易 CSV 匯出 API
系統 SHALL 提供 `GET /api/transactions/export`，並使用與交易查詢 API 相同的 filter 契約輸出 CSV。

#### Scenario: 以相同條件匯出 CSV
- **WHEN** 前端呼叫 `GET /api/transactions/export?month=2026-03&bank_code=CTBC`
- **THEN** API 會輸出與相同篩選條件一致的 CSV 內容

#### Scenario: CSV 使用 UTF-8 BOM 編碼
- **WHEN** 前端下載 CSV 檔案
- **THEN** 檔案使用 UTF-8 with BOM 編碼（`\xEF\xBB\xBF` 前綴），確保 Excel 直接開啟時正確顯示中文

#### Scenario: CSV 欄位格式
- **WHEN** CSV 檔案被產生
- **THEN** 欄位依序為：交易日期、記帳日期、商家名稱、金額、幣別、分類、銀行代碼、帳單月份；首行為欄位標題

#### Scenario: CSV 檔名包含篩選條件
- **WHEN** 前端下載 CSV 檔案
- **THEN** Content-Disposition header 的檔名格式為 `ccas-transactions-{YYYY-MM}[-{bank_code}].csv`，其中 bank_code 僅在有指定時加入
