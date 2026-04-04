"""應用程式設定模組。

透過 pydantic-settings 從環境變數或 .env 檔案載入設定值。
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import PrivateAttr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.types import ENV_FILE_SENTINEL, DotenvType

_APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ENV_FILES = (_APP_ROOT / ".env", _APP_ROOT.parent / ".env")
_SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"


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
        env_file=_DEFAULT_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./data/ccas.db"
    telegram_bot_token: str
    telegram_chat_id: str
    gmail_credentials_path: str = "./data/credentials.json"
    gmail_token_path: str = "./data/token.json"
    staging_dir: str = "./data/staging"
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
    scheduler_api_base_url: str = ""
    telegram_allowed_chat_ids: str = ""

    _env_map: dict[str, str] = PrivateAttr(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        raw = kwargs.get("_env_file", ENV_FILE_SENTINEL)
        is_override = raw is not ENV_FILE_SENTINEL
        super().__init__(**kwargs)
        # model_post_init already built _env_map from model_config default.
        # Rebuild from the caller-supplied _env_file if it was overridden.
        if is_override:
            _build_env_map(self, raw)

    def model_post_init(self, __context: Any) -> None:
        """Merge .env file values with os.environ for dynamic key lookups.

        os.environ takes precedence over .env file values.
        """
        env_file = self.model_config.get("env_file", _DEFAULT_ENV_FILES)
        _build_env_map(self, env_file)

    @field_validator(
        "gmail_credentials_path",
        "gmail_token_path",
        "staging_dir",
        mode="after",
    )
    @classmethod
    def _normalize_path_settings(cls, value: str) -> str:
        return str(_resolve_path_value(value))

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return _normalize_sqlite_url(value)

    def get_pdf_password(self, bank_code: str) -> str | None:
        """取得指定銀行的 PDF 解密密碼。

        從環境變數 ``PDF_PASSWORD_{BANK_CODE}`` 讀取。

        Args:
            bank_code: 銀行代碼（不分大小寫）。

        Returns:
            密碼字串；若未設定則回傳 None。
        """
        key = f"PDF_PASSWORD_{bank_code.upper()}"
        return self._env_map.get(key)

    def get_frontend_origins(self) -> list[str]:
        """解析允許攜帶 cookie 的前端來源清單。"""
        return [
            item.strip() for item in self.frontend_origins.split(",") if item.strip()
        ]


def _build_env_map(
    settings: Settings,
    env_file: DotenvType | None,
) -> None:
    """Build ``_env_map`` from *env_file* merged with ``os.environ``.

    ``os.environ`` takes precedence over .env file values.
    ``dotenv_values`` returns ``{}`` safely when file is absent (e.g. CI).
    """
    if env_file is None:
        file_values: dict[str, str | None] = {}
    elif isinstance(env_file, (str, Path)):
        file_values = dotenv_values(env_file)
    elif isinstance(env_file, (list, tuple)):
        file_values = {}
        for path in env_file:
            file_values.update(dotenv_values(path))
    else:
        file_values = {}
    merged = {k: v for k, v in file_values.items() if v is not None}
    merged.update(os.environ)
    object.__setattr__(settings, "_env_map", merged)


def _resolve_path_value(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (_APP_ROOT / path).resolve()


def _normalize_sqlite_url(value: str) -> str:
    if not value.startswith(_SQLITE_ASYNC_PREFIX):
        return value

    raw_path = value.removeprefix(_SQLITE_ASYNC_PREFIX)
    if raw_path == ":memory:" or raw_path.startswith("/"):
        return value

    normalized = _resolve_path_value(raw_path)
    return f"{_SQLITE_ASYNC_PREFIX}{normalized.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取得應用程式設定單例。

    使用 lru_cache 確保整個生命週期只建立一次 Settings 實例。
    """
    return Settings()  # pyright: ignore[reportCallIssue]
