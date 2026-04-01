## MODIFIED Requirements

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
- `telegram_allowed_chat_ids`（預設 `""`）— 逗號分隔的白名單 chat_id
- 一個動態方法 `get_pdf_password(bank_code: str) -> str | None`，從 `.env` 檔與環境變數查詢銀行對應的 PDF 密碼（環境變數優先於 `.env`）
- 一個私有 `_env_map` 屬性，在初始化時合併 `.env` 檔與 `os.environ` 的鍵值對，供動態鍵查詢使用

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

#### Scenario: 從 .env 檔查詢銀行 PDF 密碼
- **WHEN** `.env` 檔中包含 `PDF_PASSWORD_CTBC=mypassword`（未 shell export），並呼叫 `settings.get_pdf_password("CTBC")`
- **THEN** 會回傳 `"mypassword"`

#### Scenario: 環境變數優先於 .env 檔的 PDF 密碼
- **WHEN** `.env` 檔中包含 `PDF_PASSWORD_CTBC=file_pw`，且環境變數中有 `PDF_PASSWORD_CTBC=env_pw`
- **THEN** `settings.get_pdf_password("CTBC")` 回傳 `"env_pw"`

#### Scenario: PDF 密碼不區分大小寫查詢
- **WHEN** 呼叫 `settings.get_pdf_password("ctbc")`，且 `PDF_PASSWORD_CTBC=mypassword` 存在
- **THEN** 會回傳 `"mypassword"`

#### Scenario: PDF 密碼規則不存在
- **WHEN** 呼叫 `settings.get_pdf_password("UNKNOWN_BANK")`，且該銀行的密碼不存在於 `.env` 或環境變數
- **THEN** 會回傳 `None`

#### Scenario: telegram_allowed_chat_ids 從 .env 載入
- **WHEN** `.env` 檔中包含 `TELEGRAM_ALLOWED_CHAT_IDS=123,456`
- **THEN** `settings.telegram_allowed_chat_ids` 等於 `"123,456"`

#### Scenario: telegram_allowed_chat_ids 預設為空字串
- **WHEN** 未設定 `TELEGRAM_ALLOWED_CHAT_IDS`
- **THEN** `settings.telegram_allowed_chat_ids` 等於 `""`
