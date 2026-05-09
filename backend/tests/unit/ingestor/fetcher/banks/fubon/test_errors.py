"""Structural tests for FUBON internal error hierarchy."""

from __future__ import annotations

from ccas.ingestor.fetcher.banks.fubon.errors import (
    FubonFlowError,
    FubonLoginError,
    FubonRedirectError,
    FubonSessionError,
)


class TestErrorHierarchy:
    def test_redirect_error_is_flow_error(self):
        assert issubclass(FubonRedirectError, FubonFlowError)

    def test_session_error_is_flow_error(self):
        assert issubclass(FubonSessionError, FubonFlowError)

    def test_login_error_is_flow_error(self):
        assert issubclass(FubonLoginError, FubonFlowError)

    def test_all_are_exceptions(self):
        assert issubclass(FubonFlowError, Exception)


class TestFubonLoginError:
    def test_attributes(self):
        err = FubonLoginError("id_wrong", raw_code=1001, message="身分證字號不正確")
        assert err.code == "id_wrong"
        assert err.raw_code == 1001
        assert err.raw_message == "身分證字號不正確"

    def test_str_contains_all_fields(self):
        err = FubonLoginError("captcha_wrong", raw_code=9999, message="驗證碼錯誤")
        s = str(err)
        assert "captcha_wrong" in s
        assert "9999" in s
        assert "驗證碼錯誤" in s

    def test_defaults(self):
        err = FubonLoginError("unknown")
        assert err.raw_code is None
        assert err.raw_message == ""
