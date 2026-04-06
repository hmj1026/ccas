## 1. 更新設定檔

- [x] 1.1 修改 `config/banks.yaml`：CTBC 的 `gmail_filter` 改為 `from:ebill@estats.ctbcbank.com subject:信用卡電子帳單`
- [x] 1.2 修改 `config/banks.example.yaml`：同步更新 CTBC 的 `gmail_filter`

## 2. 更新 DB

- [x] 2.1 執行 `python -m ccas.tools.bank_configs --apply` 將新 filter 寫入 DB

## 3. 驗證

- [x] 3.1 執行 `python -m ccas.pipeline --bank CTBC`，確認 ingest stage `staged > 0`（找到 CTBC 信用卡電子帳單）
