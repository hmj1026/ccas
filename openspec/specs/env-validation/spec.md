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

