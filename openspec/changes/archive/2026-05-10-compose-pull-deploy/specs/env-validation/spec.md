## ADDED Requirements

### Requirement: CCAS_VERSION 變數驗證

`.env.example` 與 `docker/example.env` SHALL 包含 `CCAS_VERSION` 變數，預設值為 `release`。`scripts/check-env.sh` SHALL 將 `CCAS_VERSION` 視為選填（有預設值），但若使用者顯式設定，其值 MUST 符合 `release` 或 `v\d+(\.\d+){0,2}` 之一，否則驗證失敗。

#### Scenario: 預設 release 值通過驗證

- **WHEN** `.env` 未設定 `CCAS_VERSION` 或設為 `release`
- **THEN** `check-env.sh` SHALL 通過驗證

#### Scenario: 精確版本格式驗證

- **WHEN** `.env` 設定 `CCAS_VERSION=v0.1.0`、`v0.1` 或 `v0`
- **THEN** `check-env.sh` SHALL 通過驗證

#### Scenario: 非法格式 fail-fast

- **WHEN** `.env` 設定 `CCAS_VERSION=latest` 或 `0.1.0`（缺 v 前綴）或 `dev`
- **THEN** `check-env.sh` SHALL 以非零 exit code 退出，訊息指出 `CCAS_VERSION` 格式不符 `release` 或 `vX.Y.Z`

### Requirement: CCAS_*_LOCATION 路徑變數驗證

`.env.example` 與 `docker/example.env` SHALL 包含 `CCAS_DATA_LOCATION`、`CCAS_CONFIG_LOCATION`、`CCAS_LOG_LOCATION` 三個變數，皆有預設值（`./data`、`./config`、`./logs`），三者皆為選填。`scripts/check-env.sh` 驗證時 SHALL 不阻擋未設定的情況，但若使用者顯式設定空字串（如 `CCAS_DATA_LOCATION=`），SHALL 視為錯誤。

#### Scenario: 未設定使用預設

- **WHEN** `.env` 未設定 `CCAS_DATA_LOCATION`
- **THEN** `check-env.sh` SHALL 通過驗證，docker compose SHALL 使用預設 `./data`

#### Scenario: 顯式空值報錯

- **WHEN** `.env` 設定 `CCAS_DATA_LOCATION=`（空字串）
- **THEN** `check-env.sh` SHALL 以非零 exit code 退出，訊息指出該變數已設定但為空

#### Scenario: 絕對路徑與相對路徑皆接受

- **WHEN** `.env` 設定 `CCAS_DATA_LOCATION=/mnt/external` 或 `CCAS_DATA_LOCATION=./custom-data`
- **THEN** `check-env.sh` SHALL 通過驗證，由 docker compose 解析掛載

### Requirement: docker/example.env 與 .env.example 變數同步性

系統 SHALL 維護 `.env.example`（dev / 完整變數）與 `docker/example.env`（prod / 最小必要變數）兩份範本。所有在 `docker/example.env` 出現的變數 SHALL 同時存在於 `.env.example`（反向不必），且兩處變數名稱、預設值、註解 SHALL 一致。CI SHALL 提供腳本驗證兩檔同步性。

#### Scenario: docker/example.env 為 .env.example 的子集

- **WHEN** 比對兩份範本中的變數名稱
- **THEN** `docker/example.env` 中每個變數 SHALL 在 `.env.example` 中找到同名定義

#### Scenario: 共同變數預設值一致

- **WHEN** `CCAS_VERSION` 同時出現在兩份範本
- **THEN** 兩處的預設值（`release`）與註解語意 SHALL 一致

#### Scenario: CI 驗證腳本偵測偏差

- **WHEN** 開發者僅修改 `.env.example` 中的 `CCAS_VERSION` 預設值，未同步 `docker/example.env`
- **THEN** CI 上的同步驗證腳本 SHALL 報錯並阻擋 PR 合入

### Requirement: CCAS_PORT 對外服務 port 變數驗證

`.env.example` 與 `docker/example.env` SHALL 包含 `CCAS_PORT` 變數，預設值為 `8080`。`scripts/check-env.sh` SHALL 將 `CCAS_PORT` 視為選填（有預設值），但若顯式設定，其值 MUST 為 1-65535 範圍內整數，否則驗證失敗。

#### Scenario: 預設值通過驗證

- **WHEN** `.env` 未設定 `CCAS_PORT`
- **THEN** `check-env.sh` SHALL 通過驗證，docker compose SHALL 使用預設 `8080`

#### Scenario: 合法 port 通過

- **WHEN** `.env` 設定 `CCAS_PORT=12283`
- **THEN** `check-env.sh` SHALL 通過驗證

#### Scenario: 非法 port 報錯

- **WHEN** `.env` 設定 `CCAS_PORT=70000` 或 `CCAS_PORT=abc` 或 `CCAS_PORT=0`
- **THEN** `check-env.sh` SHALL 以非零 exit code 退出，訊息指出 port 範圍應為 1-65535

### Requirement: API_TOKEN 自動產生與優先序

`API_TOKEN` SHALL 為選填變數（不設定時由共用 bootstrap 自動產生），但顯式設為空字串時 SHALL 視為錯誤。backend / worker / scheduler / bot 四個 backend-family service SHALL 在啟動各自 command 前執行同一段 token bootstrap。token 取得優先序 SHALL 為：(1) 環境變數 `API_TOKEN` 已設定且非空 → 使用、(2) `${CCAS_DATA_LOCATION}/secrets/api-token` 檔案存在 → 讀取並 export、(3) 兩者皆無 → 透過 `openssl rand -hex 32` 產生，寫入該檔（權限 0600，目錄不存在則建立），export，stdout 輸出顯著 INFO 訊息含檔案路徑。

#### Scenario: 環境變數優先

- **WHEN** `.env` 設定 `API_TOKEN=user-supplied-token`，且 `${CCAS_DATA_LOCATION}/secrets/api-token` 存在但內容不同
- **THEN** entrypoint SHALL 使用環境變數的值，secrets 檔內容 SHALL 不被覆蓋亦不被讀取

#### Scenario: 既有 secrets 檔保留

- **WHEN** `.env` 未設定 `API_TOKEN`，但 `${CCAS_DATA_LOCATION}/secrets/api-token` 已存在（來自首次啟動）
- **THEN** entrypoint SHALL 讀取既有檔案內容並 export，**不**重新產生新值，保證 token 跨重啟一致

#### Scenario: worker / scheduler / bot 載入同一 token

- **WHEN** `.env` 未設定 `API_TOKEN`，backend 首次啟動已產生 `${CCAS_DATA_LOCATION}/secrets/api-token`
- **THEN** worker / scheduler / bot 啟動時 SHALL 從同一檔案讀取並 export `API_TOKEN`，`Settings.api_token` SHALL 可正常建立，scheduler SHALL 能用該 token 呼叫 backend API

#### Scenario: 首次啟動產生並落地

- **WHEN** `.env` 未設定 `API_TOKEN` 且 `${CCAS_DATA_LOCATION}/secrets/api-token` 不存在
- **THEN** entrypoint SHALL 產生 32-byte random hex、寫入該檔（權限 0600）、export 至當前 process、stdout 輸出 `[INFO] 已自動產生 API_TOKEN，請至 <絕對路徑> 取得（首次啟動）`

#### Scenario: 顯式空值報錯

- **WHEN** `.env` 設定 `API_TOKEN=`（空字串）
- **THEN** `check-env.sh` SHALL 以非零 exit code 退出，訊息指出該變數已設定但為空
