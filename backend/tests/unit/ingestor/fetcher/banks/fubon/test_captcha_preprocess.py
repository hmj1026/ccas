"""Unit tests for captcha image preprocessing."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from ccas.ingestor.fetcher.banks.fubon.captcha import _otsu_threshold, _preprocess

FIXTURES = Path(__file__).parents[5] / "fixtures" / "fubon" / "captcha_samples"


def _make_jpeg(width: int = 60, height: int = 30, color: int = 128) -> bytes:
    img = Image.new("L", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestPreprocess:
    def test_returns_bytes(self) -> None:
        result = _preprocess(_make_jpeg())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_jpeg(self) -> None:
        result = _preprocess(_make_jpeg())
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_output_is_grayscale(self) -> None:
        rgb_buf = io.BytesIO()
        Image.new("RGB", (60, 30), (255, 0, 0)).save(rgb_buf, format="JPEG")
        result = _preprocess(rgb_buf.getvalue())
        img = Image.open(io.BytesIO(result))
        assert img.mode in ("L", "1")

    def test_corrupt_input_returns_original(self) -> None:
        bad_bytes = b"not a jpeg at all"
        result = _preprocess(bad_bytes)
        assert result == bad_bytes

    def test_empty_input_returns_original(self) -> None:
        result = _preprocess(b"")
        assert result == b""

    def test_real_fixture_produces_high_contrast(self) -> None:
        samples = sorted(FIXTURES.glob("*.jpg"))
        if not samples:
            return
        raw = samples[0].read_bytes()
        processed = _preprocess(raw)
        img = Image.open(io.BytesIO(processed)).convert("L")
        hist = img.histogram()
        dark = sum(hist[:64])
        bright = sum(hist[192:])
        total = sum(hist)
        ratio = (dark + bright) / total
        assert ratio > 0.8, "binarization should push pixels to extremes"


class TestOtsuThreshold:
    def test_uniform_image(self) -> None:
        img = Image.new("L", (10, 10), 128)
        t = _otsu_threshold(img)
        assert 0 <= t <= 255

    def test_bimodal_image(self) -> None:
        img = Image.new("L", (20, 10), 50)
        img.paste(Image.new("L", (20, 5), 200), (0, 0))
        t = _otsu_threshold(img)
        assert 50 <= t <= 200, f"bimodal threshold should be between modes, got {t}"
