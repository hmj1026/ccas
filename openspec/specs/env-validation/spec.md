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

### Requirement: FUBON 專屬環境變數分級與格式驗證

`.env.example` SHALL 將以下 FUBON 專屬變數標示為「可選」（沒設時 FUBON fetcher 會明確跳過，不影響其他銀行）：`FUBON_ID_NUMBER`、`FUBON_BIRTHDAY`、`FUBON_CAPTCHA_MAX_RETRIES`、`FUBON_CAPTCHA_FALLBACK_LLM`。當任一變數被設定時，`Settings` pydantic validator SHALL 強制檢查格式。

#### Scenario: 未設定 FUBON credentials 不影響 check-env.sh 通過

- **WHEN** `.env` 完全沒有任何 `FUBON_*` 變數但所有必要變數齊全
- **THEN** `scripts/check-env.sh` SHALL 以 exit code 0 通過，並在可選變數警告區列出 `FUBON_ID_NUMBER`、`FUBON_BIRTHDAY` 為「未設定 → FUBON 自動下載停用」

#### Scenario: FUBON_ID_NUMBER 格式錯誤

- **WHEN** `FUBON_ID_NUMBER=abc12345` 或其他不符 `^[A-Z][12]\d{8}$` 的值
- **THEN** `Settings` 建立 SHALL raise `ValueError`，訊息包含 `FUBON_ID_NUMBER must be 10 chars`

#### Scenario: FUBON_BIRTHDAY 格式錯誤

- **WHEN** `FUBON_BIRTHDAY=1985-01-01`（西元格式，不是民國 7 碼）
- **THEN** `Settings` 建立 SHALL raise `ValueError`，訊息包含 `FUBON_BIRTHDAY must be ROC 7 digits`

#### Scenario: FUBON_CAPTCHA_MAX_RETRIES 預設值

- **WHEN** `.env` 沒設 `FUBON_CAPTCHA_MAX_RETRIES`
- **THEN** `Settings.fubon_captcha_max_retries` SHALL 為 `7`

#### Scenario: FUBON_CAPTCHA_FALLBACK_LLM 預設關閉

- **WHEN** `.env` 沒設 `FUBON_CAPTCHA_FALLBACK_LLM`
- **THEN** `Settings.fubon_captcha_fallback_llm` SHALL 為 `False`

#### Scenario: FUBON_CAPTCHA_FALLBACK_LLM 開啟但 anthropic 未安裝

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=1` 且 `anthropic` SDK 未安裝（未裝 `fubon-llm` extra）
- **THEN** `FubonFetcher.fetch_pdf()` 首次被呼叫時 SHALL raise `FetchError(reason="llm_fallback_sdk_missing")`

### Requirement: Legacy PDF 密碼環境變數校驗

系統 SHALL 允許每家銀行設定 `PDF_PASSWORD_<BANK>_LEGACY_1` 至 `PDF_PASSWORD_<BANK>_LEGACY_5` 共 5 組選用 legacy 密碼。env 驗證腳本 MUST NOT 將 legacy 密碼標記為必要，但若使用者設定了任一 legacy 變數，其值 MUST 非空字串，否則驗證失敗。

#### Scenario: 未設定 legacy 不視為錯誤

- **WHEN** `.env` 只含 `PDF_PASSWORD_TAISHIN` 而無任何 `_LEGACY_N`
- **THEN** `scripts/check-env.sh` SHALL 以 exit code 0 退出

#### Scenario: Legacy 變數設定但值為空字串

- **WHEN** `.env` 含 `PDF_PASSWORD_TAISHIN_LEGACY_1=`（空值）
- **THEN** 驗證腳本 SHALL 報錯並以非零 exit code 退出，訊息指出該變數已設定但為空

#### Scenario: 超過 LEGACY_5 的變數被忽略

- **WHEN** `.env` 含 `PDF_PASSWORD_TAISHIN_LEGACY_6=xxx`
- **THEN** 系統 SHALL 忽略該變數（不讀入 Settings），驗證腳本不報錯

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
