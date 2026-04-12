"""Tests for FUBON-related Settings fields.

FUBON credentials (national_id / roc_birthday) themselves are read via
``Settings.get_bank_credential``; these tests only cover the tuning-knob
fields that live directly on ``Settings``.
"""

from __future__ import annotations

import pytest

from ccas.config import Settings

_REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "t",
    "TELEGRAM_CHAT_ID": "1",
    "API_TOKEN": "tok",
}


def _setup_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    for k in (
        "FUBON_CAPTCHA_MAX_RETRIES",
        "FUBON_CAPTCHA_FALLBACK_LLM",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


def test_fubon_captcha_max_retries_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.fubon_captcha_max_retries == 7


def test_fubon_captcha_max_retries_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    monkeypatch.setenv("FUBON_CAPTCHA_MAX_RETRIES", "3")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.fubon_captcha_max_retries == 3


def test_fubon_captcha_max_retries_out_of_range_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    monkeypatch.setenv("FUBON_CAPTCHA_MAX_RETRIES", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_fubon_captcha_fallback_llm_default_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.fubon_captcha_fallback_llm is False


def test_fubon_captcha_fallback_llm_truthy_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    monkeypatch.setenv("FUBON_CAPTCHA_FALLBACK_LLM", "true")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.fubon_captcha_fallback_llm is True


def test_anthropic_api_key_default_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.anthropic_api_key.get_secret_value() == ""


def test_anthropic_api_key_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_required(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"


def test_anthropic_api_key_not_leaked_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SecretStr must hide the value in repr() / model_dump_json()."""
    _setup_required(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret-xyz")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert "sk-ant-super-secret-xyz" not in repr(settings)
    assert "sk-ant-super-secret-xyz" not in str(settings.anthropic_api_key)
