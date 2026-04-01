"""chat_id 白名單驗證的單元測試。"""

from ccas.bot.auth import is_chat_allowed, load_allowed_chat_ids


class TestLoadAllowedChatIds:
    """load_allowed_chat_ids 測試。"""

    def test_loads_comma_separated_ids(self):
        result = load_allowed_chat_ids("111,222,333")
        assert result == frozenset({111, 222, 333})

    def test_single_id(self):
        result = load_allowed_chat_ids("42")
        assert result == frozenset({42})

    def test_empty_string_returns_empty(self):
        result = load_allowed_chat_ids("")
        assert result == frozenset()

    def test_whitespace_only_returns_empty(self):
        result = load_allowed_chat_ids("   ")
        assert result == frozenset()

    def test_whitespace_handling(self):
        result = load_allowed_chat_ids(" 111 , 222 , ")
        assert result == frozenset({111, 222})

    def test_returns_frozenset(self):
        result = load_allowed_chat_ids("1")
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
