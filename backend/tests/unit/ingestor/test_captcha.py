"""CAPTCHA OCR solve_captcha() unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ccas.ingestor.fetcher.base import FetchError
from ccas.ingestor.fetcher.captcha import solve_captcha


class TestSolveCaptcha:
    """solve_captcha() tests."""

    @patch("ccas.ingestor.fetcher.captcha.pytesseract", create=True)
    @patch("ccas.ingestor.fetcher.captcha.Image", create=True)
    def test_returns_recognized_string(self, mock_image_mod, mock_tesseract):
        """Returns the OCR-recognized string from the CAPTCHA image."""
        # Arrange: mock PIL.Image.open and pytesseract.image_to_string
        mock_img = MagicMock()
        mock_image_mod.open.return_value = mock_img
        mock_tesseract.image_to_string.return_value = "AB12cd\n"
        mock_tesseract.TesseractNotFoundError = Exception

        with (
            patch.dict("sys.modules", {"pytesseract": mock_tesseract}),
            patch.dict("sys.modules", {"PIL": MagicMock(Image=mock_image_mod)}),
            patch.dict("sys.modules", {"PIL.Image": mock_image_mod}),
        ):
            result = solve_captcha(b"\x89PNG-fake-image-data")

        assert result == "AB12cd"

    @patch("ccas.ingestor.fetcher.captcha.pytesseract", create=True)
    @patch("ccas.ingestor.fetcher.captcha.Image", create=True)
    def test_returns_empty_on_ocr_failure(self, mock_image_mod, mock_tesseract):
        """Returns empty string when OCR raises a generic exception."""
        mock_img = MagicMock()
        mock_image_mod.open.return_value = mock_img
        mock_tesseract.image_to_string.side_effect = RuntimeError("OCR failed")
        mock_tesseract.TesseractNotFoundError = type(
            "TesseractNotFoundError", (Exception,), {}
        )

        with (
            patch.dict("sys.modules", {"pytesseract": mock_tesseract}),
            patch.dict("sys.modules", {"PIL": MagicMock(Image=mock_image_mod)}),
            patch.dict("sys.modules", {"PIL.Image": mock_image_mod}),
        ):
            result = solve_captcha(b"\x89PNG-fake")

        assert result == ""

    def test_raises_fetch_error_on_missing_tesseract(self):
        """Raises FetchError when pytesseract is not installed."""
        import sys

        # Temporarily hide pytesseract and PIL from imports
        saved_modules: dict[str, object] = {}
        for mod_name in ("pytesseract", "PIL", "PIL.Image"):
            if mod_name in sys.modules:
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        try:
            with (
                patch.dict(
                    "sys.modules",
                    {"pytesseract": None, "PIL": None, "PIL.Image": None},
                ),
                pytest.raises(FetchError, match="tesseract"),
            ):
                # Re-import to trigger fresh import attempt
                from importlib import reload

                import ccas.ingestor.fetcher.captcha as captcha_mod

                reload(captcha_mod)
                captcha_mod.solve_captcha(b"\x89PNG-fake")
        finally:
            # Restore modules
            for mod_name, mod in saved_modules.items():
                sys.modules[mod_name] = mod  # type: ignore[assignment]

    @patch("ccas.ingestor.fetcher.captcha.pytesseract", create=True)
    @patch("ccas.ingestor.fetcher.captcha.Image", create=True)
    def test_raises_fetch_error_on_tesseract_not_found(
        self, mock_image_mod, mock_tesseract
    ):
        """Raises FetchError when tesseract binary is not available."""

        class TesseractNotFoundError(Exception):
            pass

        mock_img = MagicMock()
        mock_image_mod.open.return_value = mock_img
        mock_tesseract.TesseractNotFoundError = TesseractNotFoundError
        mock_tesseract.image_to_string.side_effect = TesseractNotFoundError(
            "tesseract not found"
        )

        with (
            patch.dict("sys.modules", {"pytesseract": mock_tesseract}),
            patch.dict("sys.modules", {"PIL": MagicMock(Image=mock_image_mod)}),
            patch.dict("sys.modules", {"PIL.Image": mock_image_mod}),
            pytest.raises(FetchError, match="tesseract"),
        ):
            solve_captcha(b"\x89PNG-fake")
