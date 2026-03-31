# app-config Specification

## Purpose
TBD - created by archiving change foundation-setup. Update Purpose after archive.
## Requirements
### Requirement: 透過 pydantic-settings 集中管理設定
系統 SHALL 定義一個使用 pydantic-settings 的 `Settings` 類別，能從環境變數與 `.env` 檔載入設定。`Settings` 類別 SHALL 包含：
- `database_url`（預設 `"sqlite+aiosqlite:///data/ccas.db"`）— async SQLAlchemy URL
- `telegram_bot_token`（必填）
- `telegram_chat_id`（必填）
- `gmail_credentials_path`（預設 `"/data/credentials.json"`）
- `gmail_token_path`（預設 `"/data/token.json"`）
- `log_level`（預設 `"INFO"`）
- `api_host`（預設 `"0.0.0.0"`）
- `api_port`（預設 `8000`）
- `api_token`（必填，用於 Bearer Token 驗證）
- `redis_url`（預設 `"redis://localhost:6379/0"`）— RQ 任務隊列連線
- 一個動態方法 `get_pdf_password(bank_code: str) -> str | None`，從環境變數（如 `PDF_PASSWORD_BANK001`）查詢銀行對應的 PDF 密碼

#### Scenario: 從環境變數載入設定
- **WHEN** 環境變數 `TELEGRAM_BOT_TOKEN=abc123` 已設定，並建立 `Settings` 實例
- **THEN** `settings.telegram_bot_token` 等於 `"abc123"`

#### Scenario: 從 .env 檔載入設定
- **WHEN** `.env` 檔中包含 `TELEGRAM_BOT_TOKEN=abc123`，並建立 `Settings` 實例
- **THEN** `settings.telegram_bot_token` 等於 `"abc123"`

#### Scenario: 缺少必要設定時拋出錯誤
- **WHEN** 環境變數與 `.env` 中都沒有設定 `TELEGRAM_BOT_TOKEN`
- **THEN** 建立 `Settings` 實例時會拋出具有明確訊息的 `ValidationError`

#### Scenario: 套用預設值
- **WHEN** 未設定 `DATABASE_URL`
- **THEN** `settings.database_url` 等於 `"sqlite+aiosqlite:///data/ccas.db"`

#### Scenario: 查詢銀行 PDF 密碼規則
- **WHEN** 呼叫 `settings.get_pdf_password("BANK001")`，且環境變數中有 `PDF_PASSWORD_BANK001=mypassword`
- **THEN** 會回傳 `"mypassword"`

#### Scenario: PDF 密碼規則不存在
- **WHEN** 呼叫 `settings.get_pdf_password("UNKNOWN_BANK")`，且該銀行的環境變數不存在
- **THEN** 會回傳 `None`

### Requirement: Redis 連線驗證
系統 SHALL 在應用程式啟動時驗證 Redis 連線是否可用。若 Redis 連線失敗，系統 SHALL 記錄警告但不會阻止應用程式啟動（RQ worker 為可選後台服務）。

#### Scenario: Redis 連線成功
- **WHEN** 應用程式啟動且 Redis 可連線
- **THEN** 日誌會記錄 "Redis connected" 訊息

#### Scenario: Redis 連線失敗
- **WHEN** 應用程式啟動但 Redis 無法連線
- **THEN** 日誌會記錄警告，應用程式繼續運行

### Requirement: 提供環境設定範例檔
系統 SHALL 在 `backend/` 目錄中提供 `.env.example`，列出所有設定鍵與 placeholder 值，作為必要設定的文件。

#### Scenario: 範例檔列出所有鍵值
- **WHEN** 開發者閱讀 `backend/.env.example`
- **THEN** 可以看到 `Settings` 類別中的所有設定鍵與具描述性的 placeholder 值

### Requirement: 提供設定單例存取方式
系統 SHALL 提供 `get_settings()` 函式，回傳已快取的 `Settings` 實例，並可作為 FastAPI dependency 使用。

#### Scenario: 多次請求重用同一個設定實例
- **WHEN** 多次呼叫 `get_settings()`
- **THEN** 每次都回傳相同的 `Settings` 實例，而不會重複解析設定

