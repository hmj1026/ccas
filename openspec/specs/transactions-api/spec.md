# transactions-api Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
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


### Requirement: 消費交易投影知識集中

消費交易查詢 module SHALL 從同一批資料產生完整、具型別的原生交易投影與安全 Agent
payload；網頁 adapter SHALL 無需以字串 id 拼接 metadata 字典或將 Money 字串還原為整數。
既有篩選、排序、分頁、對帳識別鍵與敏感資料拒絕規則 SHALL 保持相容。

#### Scenario: 外幣退款與零額交易維持表示法

- **WHEN** 查詢包含外幣退款、零額交易及無原始金額的交易
- **THEN** 網頁結果 SHALL 保留各交易的原始 currency、整數 amount，以及負值、零值或 null 的 original_amount
- **THEN** Agent payload SHALL 沿用既有 TWD Money 表示法，且不包含內部原生投影或 metadata

#### Scenario: 排序分頁仍保持交易資料完整

- **WHEN** 同一查詢排序後分成多頁
- **THEN** 每筆交易 SHALL 帶有自己的完整金額與幣別，不依賴額外字典配對或預設幣別
- **THEN** 敏感商家資料 SHALL 以安全錯誤拒絕，不回傳完整卡號或私人備註
