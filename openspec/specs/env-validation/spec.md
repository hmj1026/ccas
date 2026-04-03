# env-validation Specification

## Purpose
TBD - created by archiving change local-ops-overhaul. Update Purpose after archive.
## Requirements
### Requirement: 獨立 env 驗證命令

系統 SHALL 提供 `scripts/check-env.sh` 腳本，檢查 `.env` 檔案中所有必要環境變數是否存在，輸出缺漏清單。

#### Scenario: 所有必要變數齊全

- **WHEN** `.env` 包含所有 `.env.example` 中標記為必要的變數
- **THEN** 腳本 SHALL 以 exit code 0 退出，輸出驗證通過訊息

#### Scenario: 缺少必要變數

- **WHEN** `.env` 缺少一個或多個必要變數（如 `API_TOKEN`、`TELEGRAM_BOT_TOKEN`）
- **THEN** 腳本 SHALL 列出所有缺漏的變數名稱，並以 exit code 1 退出

#### Scenario: 缺少可選變數僅警告

- **WHEN** `.env` 缺少可選變數（如 `LOG_LEVEL`、`REDIS_URL`）但必要變數齊全
- **THEN** 腳本 SHALL 輸出警告訊息列出缺漏的可選變數，但以 exit code 0 退出

#### Scenario: .env 檔案不存在

- **WHEN** 專案根目錄沒有 `.env` 檔案
- **THEN** 腳本 SHALL 輸出錯誤訊息提示使用者從 `.env.example` 建立 `.env`，並以 exit code 1 退出

### Requirement: 變數分級以 .env.example 為 SSOT

系統 SHALL 以 `.env.example` 作為變數清單的唯一來源。無預設值的變數（`KEY=`）為必要，有預設值的變數（`KEY=value`）為可選。

#### Scenario: 新增環境變數自動納入驗證

- **WHEN** 開發者在 `.env.example` 新增一行 `NEW_VAR=`（無預設值）
- **THEN** `check-env.sh` SHALL 自動將 `NEW_VAR` 列為必要變數進行檢查，無需修改腳本

#### Scenario: 有預設值的變數不阻斷啟動

- **WHEN** `.env.example` 中 `LOG_LEVEL=INFO` 且 `.env` 未設定 `LOG_LEVEL`
- **THEN** 腳本 SHALL 僅輸出警告，不阻斷啟動流程

