"""OCR module unit tests.

Tests is_ocr_available() and extract_text_from_image() with mocked tesseract.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from ccas.parser import ocr


@pytest.fixture(autouse=True)
def _reset_ocr_cache():
    """Reset cached OCR availability between tests."""
    ocr.is_ocr_available.cache_clear()
    yield
    ocr.is_ocr_available.cache_clear()


class TestIsOcrAvailable:
    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_available_when_installed(self, mock_which):
        assert ocr.is_ocr_available() is True

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_not_installed(self, mock_which):
        assert ocr.is_ocr_available() is False

    @patch("shutil.which", return_value=None)
    def test_logs_warning_once(self, mock_which, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="ccas.parser.ocr"):
            ocr.is_ocr_available()
            # Second call returns cached result; no duplicate warning
            ocr.is_ocr_available()

        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) == 1
        assert "tesseract 未安裝" in warn_records[0].message

    @patch("shutil.which", return_value="/usr/bin/tesseract")
    def test_result_is_cached(self, mock_which):
        assert ocr.is_ocr_available() is True
        assert ocr.is_ocr_available() is True
        # shutil.which called only once due to functools.cache
        mock_which.assert_called_once()


class TestExtractTextFromImage:
    @patch("ccas.parser.ocr.is_ocr_available", return_value=False)
    def test_returns_empty_when_unavailable(self, mock_avail):
        img = Image.new("RGB", (100, 20))
        result = ocr.extract_text_from_image(img)
        assert result == ""

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_returns_stripped_text(self, mock_avail):
        img = Image.new("RGB", (100, 20))
        with patch("pytesseract.image_to_string", return_value="  統一超商  \n"):
            result = ocr.extract_text_from_image(img)
        assert result == "統一超商"

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_returns_empty_on_error(self, mock_avail, caplog):
        import logging

        img = Image.new("RGB", (100, 20))
        with patch(
            "pytesseract.image_to_string",
            side_effect=RuntimeError("tesseract crash"),
        ):
            with caplog.at_level(logging.WARNING, logger="ccas.parser.ocr"):
                result = ocr.extract_text_from_image(img)

        assert result == ""
        assert any("OCR 辨識失敗" in r.message for r in caplog.records)

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_uses_chi_tra_by_default(self, mock_avail):
        img = Image.new("RGB", (100, 20))
        with patch("pytesseract.image_to_string", return_value="test") as mock_ocr:
            ocr.extract_text_from_image(img)
        mock_ocr.assert_called_once_with(img, lang="chi_tra", config="--psm 7")

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_custom_language(self, mock_avail):
        img = Image.new("RGB", (100, 20))
        with patch("pytesseract.image_to_string", return_value="test") as mock_ocr:
            ocr.extract_text_from_image(img, lang="eng")
        mock_ocr.assert_called_once_with(img, lang="eng", config="--psm 7")

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_returns_empty_on_unexpected_ocr_error(self, mock_avail):
        img = Image.new("RGB", (100, 20))
        with patch("pytesseract.image_to_string", side_effect=ValueError("bad image")):
            assert ocr.extract_text_from_image(img) == ""


class TestExtractTextFromPdf:
    @patch("ccas.parser.ocr.is_ocr_available", return_value=False)
    def test_returns_empty_when_tesseract_is_unavailable(self, mock_avail, tmp_path):
        with patch("pdfplumber.open") as open_pdf:
            assert ocr.extract_text_from_pdf(tmp_path / "scan.pdf") == ""
        open_pdf.assert_not_called()

    @patch("ccas.parser.ocr.is_ocr_available", return_value=True)
    def test_ocr_scanned_pages_in_order(self, mock_avail, tmp_path):
        page1 = MagicMock()
        page2 = MagicMock()
        pdf = type("Pdf", (), {"pages": [page1, page2]})()
        with (
            patch("pdfplumber.open") as open_pdf,
            patch(
                "ccas.parser.ocr.extract_text_from_image",
                side_effect=["page 1", " page 2 "],
            ),
        ):
            open_pdf.return_value.__enter__.return_value = pdf
            assert ocr.extract_text_from_pdf(tmp_path / "scan.pdf") == "page 1\npage 2"


def test_parse_ocr_text_extracts_summary_with_non_rules_confidence() -> None:
    result = ocr.parse_ocr_text(
        "中國信託信用卡帳單\n帳單月份：2026年03月\n"
        "繳費截止日：2026/04/15\n本期應繳總額：NT$ 1,000",
        "CTBC",
    )

    assert result is not None
    assert result.parse_method == "ocr"
    assert result.parse_confidence == 0.95
    assert result.needs_review is False


def test_parse_ocr_text_returns_low_confidence_for_missing_summary_field() -> None:
    result = ocr.parse_ocr_text("帳單月份：2026年03月\n本期應繳總額：NT$ 1,000", "CTBC")

    assert result is not None
    assert result.parse_confidence < 0.85
    assert result.needs_review is True
