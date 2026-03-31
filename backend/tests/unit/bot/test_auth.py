"""chat_id 白名單驗證的單元測試。"""

import os

import pytest

from ccas.bot.auth import is_chat_allowed, load_allowed_chat_ids


class TestLoadAllowedChatIds:
    """load_allowed_chat_ids 測試。"""

    def test_loads_comma_separated_ids(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111,222,333")
        result = load_allowed_chat_ids()
        assert result == frozenset({111, 222, 333})

    def test_single_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "42")
        result = load_allowed_chat_ids()
        assert result == frozenset({42})

    def test_empty_string_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
        result = load_allowed_chat_ids()
        assert result == frozenset()

    def test_unset_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
        result = load_allowed_chat_ids()
        assert result == frozenset()

    def test_whitespace_handling(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", " 111 , 222 , ")
        result = load_allowed_chat_ids()
        assert result == frozenset({111, 222})

    def test_returns_frozenset(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1")
        result = load_allowed_chat_ids()
        assert isinstance(result, frozenset)


class TestIsChatAllowed:
    """is_chat_allowed 測試。"""

    def test_allowed_chat_id(self):
        allowed = frozenset({100, 200})
        assert is_chat_allowed(100, allowed) is True

    def test_denied_chat_id(self):
        allowed = frozenset({100, 200})
        assert is_chat_allowed(999, allowed) is False

    def test_empty_whitelist_denies_all(self):
        allowed: frozenset[int] = frozenset()
        assert is_chat_allowed(100, allowed) is False
