"""Tests for Settings._env_map and _env_file override behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccas import config as config_module
from ccas.config import Settings

_REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "test-token",
    "TELEGRAM_CHAT_ID": "12345",
    "API_TOKEN": "test-api-token",
}
_PATH_ENV_KEYS = (
    "DATABASE_URL",
    "GMAIL_CREDENTIALS_PATH",
    "GMAIL_TOKEN_PATH",
    "STAGING_DIR",
)


def _write_dotenv(path: Path, pairs: dict[str, str]) -> None:
    path.write_text(
        "\n".join(f"{k}={v}" for k, v in pairs.items()),
        encoding="utf-8",
    )


def _make_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    env_file_content: dict[str, str] | None = None,
    env_file_arg: str | None | object = ...,
) -> Settings:
    """Helper to build a Settings with controlled env state.

    Args:
        env_file_content: Key-value pairs to write into a temp .env file.
            If None, no temp file is created.
        env_file_arg: Value for _env_file kwarg. Use ``...`` (Ellipsis)
            to omit the kwarg entirely (let pydantic use model_config default).
    """
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    for key in _PATH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    kwargs: dict[str, object] = {}
    if env_file_content is not None:
        dotenv_path = tmp_path / ".env"
        _write_dotenv(dotenv_path, env_file_content)
        if env_file_arg is ...:
            kwargs["_env_file"] = str(dotenv_path)
        elif env_file_arg is not None:
            kwargs["_env_file"] = env_file_arg
        else:
            kwargs["_env_file"] = None
    elif env_file_arg is not ...:
        kwargs["_env_file"] = env_file_arg

    return Settings(**kwargs)  # pyright: ignore[reportCallIssue]


def _sqlite_absolute_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve().as_posix()}"


def _backend_root() -> Path:
    return Path(config_module.__file__).resolve().parents[2]


class TestEnvMapWithCustomEnvFile:
    """_env_map should load from the caller-supplied _env_file."""

    def test_env_map_respects_custom_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"PDF_PASSWORD_CTBC": "secret123"},
        )
        assert settings._env_map.get("PDF_PASSWORD_CTBC") == "secret123"

    def test_get_pdf_password_from_custom_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"PDF_PASSWORD_FUBON": "mypass"},
        )
        assert settings.get_pdf_password("fubon") == "mypass"

    def test_os_environ_takes_precedence_over_custom_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "from_env")
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"PDF_PASSWORD_CTBC": "from_file"},
        )
        assert settings.get_pdf_password("ctbc") == "from_env"


class TestEnvMapWithNoneEnvFile:
    """_env_file=None should skip dotenv loading entirely."""

    def test_env_map_none_skips_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Write a file but pass _env_file=None — values should NOT appear
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"PDF_PASSWORD_CTBC": "should_not_load"},
            env_file_arg=None,
        )
        assert settings._env_map.get("PDF_PASSWORD_CTBC") is None

    def test_env_map_none_still_has_os_environ(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PDF_PASSWORD_FUBON", "env_val")
        settings = _make_settings(monkeypatch, tmp_path, env_file_arg=None)
        assert settings._env_map.get("PDF_PASSWORD_FUBON") == "env_val"


class TestPathNormalization:
    """Path-like settings should be anchored consistently."""

    def test_defaults_resolve_under_backend_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(monkeypatch, tmp_path, env_file_arg=None)
        backend_root = _backend_root()

        assert settings.database_url == _sqlite_absolute_url(
            backend_root / "data/ccas.db"
        )
        assert settings.gmail_credentials_path == str(
            (backend_root / "data/credentials.json").resolve()
        )
        assert settings.gmail_token_path == str(
            (backend_root / "data/token.json").resolve()
        )
        assert settings.staging_dir == str((backend_root / "data/staging").resolve())

    def test_relative_overrides_resolve_under_backend_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={
                "DATABASE_URL": "sqlite+aiosqlite:///./custom/ccas.db",
                "GMAIL_CREDENTIALS_PATH": "./secrets/credentials.json",
                "GMAIL_TOKEN_PATH": "./secrets/token.json",
                "STAGING_DIR": "./custom/staging",
            },
        )
        backend_root = _backend_root()

        assert settings.database_url == _sqlite_absolute_url(
            backend_root / "custom/ccas.db"
        )
        assert settings.gmail_credentials_path == str(
            (backend_root / "secrets/credentials.json").resolve()
        )
        assert settings.gmail_token_path == str(
            (backend_root / "secrets/token.json").resolve()
        )
        assert settings.staging_dir == str((backend_root / "custom/staging").resolve())

    def test_absolute_overrides_are_preserved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={
                "DATABASE_URL": "sqlite+aiosqlite:////data/ccas.db",
                "GMAIL_CREDENTIALS_PATH": "/data/credentials.json",
                "GMAIL_TOKEN_PATH": "/data/token.json",
                "STAGING_DIR": "/data/staging",
            },
        )

        assert settings.database_url == "sqlite+aiosqlite:////data/ccas.db"
        assert settings.gmail_credentials_path == "/data/credentials.json"
        assert settings.gmail_token_path == "/data/token.json"
        assert settings.staging_dir == "/data/staging"


class TestMasterKeyManager:
    """Settings.master_key_manager 為 lazy property，首次存取時 instantiate。"""

    def test_master_key_path_default_resolves_under_backend_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        settings = _make_settings(monkeypatch, tmp_path, env_file_arg=None)

        assert settings.master_key_path == str(
            (_backend_root() / "data/secrets/master.key").resolve()
        )

    def test_master_key_path_absolute_override_preserved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        target = tmp_path / "custom-secrets" / "master.key"
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"MASTER_KEY_PATH": str(target)},
        )

        assert settings.master_key_path == str(target.resolve())

    def test_master_key_manager_is_lazy_and_cached(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        target = tmp_path / "secrets" / "master.key"
        settings = _make_settings(
            monkeypatch,
            tmp_path,
            env_file_content={"MASTER_KEY_PATH": str(target)},
        )

        # File should NOT exist yet — Settings init must not touch the filesystem.
        assert not target.exists()

        mgr1 = settings.master_key_manager
        mgr2 = settings.master_key_manager

        assert mgr1 is mgr2
        # First decrypt/encrypt triggers load_or_create.
        ct = mgr1.encrypt("hello")
        assert mgr1.decrypt(ct) == "hello"
        assert target.exists()
