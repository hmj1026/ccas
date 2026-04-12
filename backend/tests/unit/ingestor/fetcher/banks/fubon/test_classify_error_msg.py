"""Verify _classify_error_msg covers user-guide §5 troubleshooting table."""

from ccas.ingestor.fetcher.banks.fubon.client import _classify_error_msg


class TestClassifyErrorMsg:
    def test_captcha_wrong(self):
        assert (
            _classify_error_msg("登入失敗, 請確認圖形驗證碼是否輸入正確")
            == "captcha_wrong"
        )

    def test_captcha_keyword_partial(self):
        assert _classify_error_msg("驗證碼錯誤") == "captcha_wrong"

    def test_id_wrong_traditional(self):
        assert _classify_error_msg("身分證字號格式錯誤") == "id_wrong"

    def test_id_wrong_simplified(self):
        assert _classify_error_msg("身份證字號不正確") == "id_wrong"

    def test_birthday_wrong_birth(self):
        assert _classify_error_msg("出生日期不符") == "birthday_wrong"

    def test_birthday_wrong_alt(self):
        assert _classify_error_msg("生日輸入錯誤") == "birthday_wrong"

    def test_record_not_found(self):
        assert _classify_error_msg("登入失敗, 查無資料") == "record_not_found"

    def test_record_not_found_alt(self):
        assert _classify_error_msg("查無此筆記錄") == "record_not_found"

    def test_empty_string_returns_unknown(self):
        assert _classify_error_msg("") == "unknown"

    def test_unrecognized_msg_returns_unknown(self):
        assert _classify_error_msg("系統維護中") == "unknown"
