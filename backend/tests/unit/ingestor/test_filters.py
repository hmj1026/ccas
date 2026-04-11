"""附件檔名黑名單過濾單元測試。"""

from ccas.ingestor.filters import should_skip_attachment


class TestShouldSkipAttachment:
    def test_sinopac_payment_slip_is_skipped(self):
        assert should_skip_attachment("SINOPAC", "永豐銀行信用卡繳款聯.pdf") is True

    def test_sinopac_statement_is_not_skipped(self):
        assert should_skip_attachment("SINOPAC", "永豐銀行信用卡帳單.pdf") is False

    def test_non_blocklisted_bank_never_skips(self):
        assert should_skip_attachment("CTBC", "任何檔名.pdf") is False

    def test_cathay_payment_slip_is_skipped(self):
        assert (
            should_skip_attachment("CATHAY", "國泰世華115年03月信用卡繳款聯.pdf")
            is True
        )

    def test_cathay_statement_is_not_skipped(self):
        assert (
            should_skip_attachment("CATHAY", "信用卡電子帳單消費明細_11503.pdf")
            is False
        )

    def test_match_is_case_insensitive(self):
        # Case-insensitive substring match (繳款聯 is CJK but guard regressions)
        assert should_skip_attachment("SINOPAC", "SINOPAC_繳款聯_2026.PDF") is True

    def test_empty_filename(self):
        assert should_skip_attachment("SINOPAC", "") is False

    def test_unknown_bank_code(self):
        assert should_skip_attachment("UNKNOWN", "繳款聯.pdf") is False
