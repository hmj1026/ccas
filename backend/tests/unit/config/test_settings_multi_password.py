"""Settings.get_pdf_passwords() multi-password support tests."""

from ccas.config import Settings


class TestGetPdfPasswords:
    """get_pdf_passwords() returns ordered tuple of candidate passwords."""

    def test_primary_only(self, monkeypatch):
        """Only primary set -> single-element tuple."""
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "primary-pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("primary-pw",)

    def test_primary_and_legacy_1(self, monkeypatch):
        """Primary + legacy_1 -> tuple ordered (primary, legacy_1)."""
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "new-pw")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_1", "old-pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("new-pw", "old-pw")

    def test_legacy_only_no_primary(self, monkeypatch):
        """Only legacy_1 set (no primary) -> single-element tuple."""
        monkeypatch.delenv("PDF_PASSWORD_TAISHIN", raising=False)
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_1", "legacy-pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("legacy-pw",)

    def test_skip_gap_in_legacy_numbers(self, monkeypatch):
        """Primary + legacy_3 (gaps 1,2 missing) -> (primary, legacy_3)."""
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "primary-pw")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_3", "legacy3-pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("primary-pw", "legacy3-pw")

    def test_legacy_6_ignored(self, monkeypatch):
        """_LEGACY_6 beyond limit is ignored."""
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "primary-pw")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_6", "should-ignore")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("primary-pw",)

    def test_no_password_set(self, monkeypatch):
        """No password env vars -> empty tuple."""
        monkeypatch.delenv("PDF_PASSWORD_UNKNOWN", raising=False)
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("UNKNOWN")

        assert result == ()

    def test_empty_string_password_excluded(self, monkeypatch):
        """Empty-string env var is treated as unset."""
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN", "")
        monkeypatch.setenv("PDF_PASSWORD_TAISHIN_LEGACY_1", "legacy-pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("TAISHIN")

        assert result == ("legacy-pw",)

    def test_case_insensitive_bank_code(self, monkeypatch):
        """Bank code is case-insensitive."""
        monkeypatch.setenv("PDF_PASSWORD_CTBC", "pw")
        monkeypatch.setenv("API_TOKEN", "test")
        settings = Settings(_env_file=None)

        result = settings.get_pdf_passwords("ctbc")

        assert result == ("pw",)
