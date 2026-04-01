"""應用程式設定模組。

透過 pydantic-settings 從環境變數或 .env 檔案載入設定值。
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """應用程式設定。

    從環境變數或 .env 檔案載入所有設定值。
    必填欄位若未提供會在啟動時拋出 ValidationError。

    Attributes:
        database_url: SQLite 非同步連線字串。
        telegram_bot_token: Telegram Bot API 權杖。
        telegram_chat_id: Telegram 通知目標聊天室 ID。
        gmail_credentials_path: Gmail API OAuth 憑證檔路徑。
        gmail_token_path: Gmail API Token 檔路徑。
        staging_dir: Gmail 附件 staging 目錄根路徑。
        log_level: 日誌等級（DEBUG / INFO / WARNING / ERROR）。
        log_format: 日誌格式（json / text）。
        api_host: API 伺服器綁定位址。
        api_port: API 伺服器連接埠。
        api_token: API 認證用 Bearer Token。
        redis_url: Redis 連線字串。
    """

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///data/ccas.db"
    telegram_bot_token: str
    telegram_chat_id: str
    gmail_credentials_path: str = "/data/credentials.json"
    gmail_token_path: str = "/data/token.json"
    staging_dir: str = "data/staging"
    log_level: str = "INFO"
    log_format: str = "json"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_token: str
    frontend_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    api_session_cookie_name: str = "ccas_session"
    api_session_max_age: int = 43200
    api_cookie_secure: bool = False
    redis_url: str = "redis://localhost:6379/0"

    def get_pdf_password(self, bank_code: str) -> str | None:
        """取得指定銀行的 PDF 解密密碼。

        從環境變數 ``PDF_PASSWORD_{BANK_CODE}`` 讀取。

        Args:
            bank_code: 銀行代碼（不分大小寫）。

        Returns:
            密碼字串；若未設定則回傳 None。
        """
        key = f"PDF_PASSWORD_{bank_code.upper()}"
        return os.environ.get(key)

    def get_frontend_origins(self) -> list[str]:
        """解析允許攜帶 cookie 的前端來源清單。"""
        return [
            item.strip() for item in self.frontend_origins.split(",") if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取得應用程式設定單例。

    使用 lru_cache 確保整個生命週期只建立一次 Settings 實例。
    """
    return Settings()  # pyright: ignore[reportCallIssue]
