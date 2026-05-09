# ctbc-bootstrap Specification

## Purpose
TBD - created by archiving change ctbc-production-ready. Update Purpose after archive.
## Requirements
### Requirement: CTBC 預設銀行配置

`banks.example.yaml` SHALL 包含可直接使用的 CTBC 銀行配置。

CTBC 的 `gmail_filter` SHALL 設定為 `from:ebill@estats.ctbcbank.com subject:信用卡電子帳單`，以匹配實際的 CTBC 信用卡電子帳單（區分於銀行對帳單的 `電子對帳單`）。

#### Scenario: 首次設定自動配置 CTBC
- **WHEN** 用戶依照 banks.example.yaml 建立 banks.yaml 並執行 bank_configs --apply
- **THEN** BankConfig 資料表 SHALL 包含 CTBC 記錄（gmail_filter=`from:ebill@estats.ctbcbank.com subject:信用卡電子帳單`、is_active=true）

### Requirement: CTBC 常見消費分類關鍵字

Seed data SHALL 包含 CTBC 帳單常見的消費分類關鍵字。

#### Scenario: 預設關鍵字涵蓋主要消費類別
- **WHEN** 執行 seed data 後分類 CTBC 交易
- **THEN** 日常消費（超商、超市、餐飲、交通、串流服務）SHALL 可被正確分類

