"""應用程式設定模組。

透過 pydantic-settings 從環境變數或 .env 檔案載入設定值。
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import dotenv_values
from pydantic import Field, PrivateAttr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.types import ENV_FILE_SENTINEL, DotenvType

if TYPE_CHECKING:
    from ccas.storage.secrets import MasterKeyManager

_APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ENV_FILES = (_APP_ROOT / ".env", _APP_ROOT.parent / ".env")
_SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"
_MAX_LEGACY_PDF_PASSWORDS = 5


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
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    gmail_credentials_path: str = "./data/credentials.json"
    gmail_token_path: str = "./data/token.json"
    staging_dir: str = "./data/staging"
    # 單筆 PDF 解析逾時（秒）。毒藥 PDF 觸發 pdfplumber 無限阻塞時，
    # asyncio.wait_for 逾時讓 worker 標記 PARSE_FAILED 並繼續下一筆。
    pdf_parse_timeout_seconds: float = 60.0
    log_level: str = "INFO"
    log_format: str = "json"
    log_dir: str = ""
    log_file_max_bytes: int = Field(default=10_485_760, gt=0)
    log_file_backup_count: int = Field(default=5, ge=0)
    log_file_prefix: str = "ccas"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Swagger UI / ReDoc / openapi.json are disabled by default; opt-in via
    # ENABLE_API_DOCS=true for development or internal debugging only.
    enable_api_docs: bool = False
    api_token: str
    # 由 entrypoint 寫入的 token / version 檔；rotate API 直接讀寫此處避免
    # 受 lru_cache 鎖住。檔案缺席時 fallback 為 ``api_token`` 與 version=1，
    # 不破壞 dev/test 的純 env 設定路徑（oauth-onboarding-ui §6）。
    api_token_path: Path = Path("./data/secrets/api-token")
    api_token_version_path: Path = Path("./data/secrets/api-token-version")
    frontend_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    api_session_cookie_name: str = "ccas_session"
    api_session_max_age: int = 43200
    # Secure-by-default: the session cookie carries the Secure flag (TLS-only)
    # unless an HTTP-only local dev explicitly opts out with
    # API_COOKIE_SECURE=false. check-env.sh blocks an HTTPS deploy that opts out.
    api_cookie_secure: bool = True
    redis_url: str = "redis://localhost:6379/0"
    scheduler_api_base_url: str = ""
    telegram_allowed_chat_ids: str = ""

    # FUBON web-fetch pipeline tuning knobs. Credentials themselves
    # (FUBON_NATIONAL_ID, FUBON_ROC_BIRTHDAY) live outside Settings and
    # are read via ``get_bank_credential("FUBON", ...)`` like other banks.
    fubon_captcha_max_retries: int = Field(default=7, ge=1, le=20)
    fubon_captcha_fallback_llm: bool = False
    fubon_captcha_archive_dir: str = ""
    fubon_manual_staging_dir: str = "./data/manual-staging/FUBON"
    anthropic_api_key: SecretStr = SecretStr("")

    # master.key 路徑（Fernet 對稱加密；oauth-onboarding-ui §1.4）。entrypoint
    # 在啟動時自動產生此檔（首次）；本欄位僅指向位置，並透過
    # ``master_key_manager`` lazy property 暴露 ``MasterKeyManager``。
    master_key_path: Path = Path("./data/secrets/master.key")

    # scheduler heartbeat 檔；BlockingScheduler 啟動後由 interval job 每 30s
    # touch 一次，docker-compose §1.11 worker/scheduler healthcheck 用 mtime
    # 判斷 scheduler 是否仍在跑。Docker 部署時透過 CCAS_DATA_LOCATION 掛在
    # /data/scheduler-heartbeat。
    scheduler_heartbeat_path: Path = Path("./data/scheduler-heartbeat")

    # 對外可見的 base URL（oauth-onboarding-ui §3.7）；用於組成 Gmail OAuth
    # callback ``redirect_uri``。預設假設透過 nginx proxy 暴露於 8080；
    # 若使用者透過外部 reverse proxy 暴露需更新此值。任何尾端 ``/`` 皆會
    # 在 ``get_public_base_url`` 中被去除以避免雙斜線。
    public_base_url: str = "http://localhost:8080"

    _env_map: dict[str, str] = PrivateAttr(default_factory=dict)
    _master_key_manager: "MasterKeyManager | None" = PrivateAttr(default=None)

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
        "fubon_manual_staging_dir",
        mode="after",
    )
    @classmethod
    def _normalize_path_settings(cls, value: str) -> str:
        return str(_resolve_path_value(value))

    @field_validator(
        "master_key_path",
        "api_token_path",
        "api_token_version_path",
        "scheduler_heartbeat_path",
        mode="after",
    )
    @classmethod
    def _normalize_path_object_settings(cls, value: Path) -> Path:
        # Path-typed fields skip the str() round-trip so callers can use the
        # Path directly without wrapping in ``Path(...)`` (issue #9 follow-up).
        return _resolve_path_value(value)

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return _normalize_sqlite_url(value)

    @field_validator("telegram_chat_id", mode="after")
    @classmethod
    def _validate_telegram_chat_id(cls, value: str) -> str:
        """Validate TELEGRAM_CHAT_ID is numeric when set.

        Empty string passes through (Telegram notify disabled). Non-empty
        values must parse as int — negative group chat ids are legal.
        Fail fast at startup instead of silently failing at notify time.
        """
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            int(stripped)
        except ValueError:
            raise ValueError(
                "TELEGRAM_CHAT_ID must be an integer chat id "
                f"(got {stripped!r}); leave empty to disable Telegram notify"
            ) from None
        return stripped

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

    def get_pdf_passwords(self, bank_code: str) -> tuple[str, ...]:
        """取得指定銀行的所有候選 PDF 解密密碼。

        依序回傳主密碼 ``PDF_PASSWORD_{BANK_CODE}`` 與
        legacy 密碼 ``PDF_PASSWORD_{BANK_CODE}_LEGACY_1`` .. ``_LEGACY_5``。
        跳過未設定或空值的項目。

        Args:
            bank_code: 銀行代碼（不分大小寫）。

        Returns:
            候選密碼 tuple（主密碼優先）；若無任何密碼則為空 tuple。
        """
        code = bank_code.upper()
        candidates: list[str] = []
        primary = self._env_map.get(f"PDF_PASSWORD_{code}")
        if primary:
            candidates.append(primary)
        for i in range(1, _MAX_LEGACY_PDF_PASSWORDS + 1):
            legacy = self._env_map.get(f"PDF_PASSWORD_{code}_LEGACY_{i}")
            if legacy:
                candidates.append(legacy)
        return tuple(candidates)

    def get_bank_credential(self, bank_code: str, key: str) -> str | None:
        """取得指定銀行的額外憑證。

        從環境變數 ``{BANK_CODE}_{KEY}`` 讀取。

        Args:
            bank_code: 銀行代碼（不分大小寫）。
            key: 憑證鍵名（不分大小寫）。

        Returns:
            憑證字串；若未設定則回傳 None。
        """
        env_key = f"{bank_code.upper()}_{key.upper()}"
        return self._env_map.get(env_key)

    def get_frontend_origins(self) -> list[str]:
        """解析允許攜帶 cookie 的前端來源清單。"""
        return [
            item.strip() for item in self.frontend_origins.split(",") if item.strip()
        ]

    def get_public_base_url(self) -> str:
        """回傳去掉尾端 ``/`` 的 public base URL。

        例：``http://localhost:8080/`` → ``http://localhost:8080``。OAuth
        ``redirect_uri`` 串接子路徑時可避免雙斜線。
        """
        return self.public_base_url.rstrip("/")

    @property
    def master_key_manager(self) -> "MasterKeyManager":
        """Lazy 取得 ``MasterKeyManager``（首次存取時 instantiate）。

        不在 ``__init__`` 讀檔；entrypoint 已負責確保 master.key 存在，
        但此處仍允許 ``MasterKeyManager.load_or_create`` 自動產生（單機 dev
        場景跳過 entrypoint 時也能用）。

        遠端缺檔時 raise 由 ``MasterKeyManager`` 處理（fail-loud）。
        """
        if self._master_key_manager is None:
            # Local import to avoid module load-time cycle (storage imports errors,
            # config also defines errors-adjacent settings).
            from ccas.storage.secrets import MasterKeyManager

            self._master_key_manager = MasterKeyManager(self.master_key_path)
        return self._master_key_manager


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
