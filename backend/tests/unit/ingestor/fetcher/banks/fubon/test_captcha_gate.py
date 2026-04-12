"""Unit tests for FUBON captcha OCR gate (ddddocr primary).

Strategy: load real captcha samples with visually-confirmed ground truth
filenames; assert that ``solve()`` either returns a result whose text matches
the filename stem (accepted) or returns ``None`` (rejected by conf/length/digit
gate). No sample may be accepted with wrong text — that would be a false
positive. The gate is expected to reach accept rate ≥ 80% on the fixture set.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ccas.ingestor.fetcher.banks.fubon import captcha

FIXTURES = Path(__file__).parents[5] / "fixtures" / "fubon" / "captcha_samples"
_MIN_ACCEPT_RATE = 0.80
_MIN_FIXTURE_COUNT = 10


def _samples() -> list[Path]:
    return sorted(FIXTURES.glob("*.jpg"))


def test_fixtures_exist() -> None:
    samples = _samples()
    assert len(samples) >= _MIN_FIXTURE_COUNT, (
        f"expected >= {_MIN_FIXTURE_COUNT} fixtures, got {len(samples)}"
    )


def test_all_samples_gate_correctness() -> None:
    """Accept rate >= 80%, false positive rate = 0."""
    samples = _samples()
    accepted: list[tuple[str, float]] = []
    rejected: list[str] = []
    for p in samples:
        gt = p.stem
        result = captcha.solve(p.read_bytes())
        if result is None:
            rejected.append(gt)
        else:
            assert result.text == gt, (
                f"false positive: sample={gt} got={result.text!r} "
                f"conf={result.confidence:.3f}"
            )
            accepted.append((gt, result.confidence))

    total = len(samples)
    accept_rate = len(accepted) / total
    assert accept_rate >= _MIN_ACCEPT_RATE, (
        f"accept rate {accept_rate:.1%} below threshold "
        f"{_MIN_ACCEPT_RATE:.0%} "
        f"(accepted={len(accepted)}, rejected={len(rejected)}, total={total})"
    )
    assert len(accepted) + len(rejected) == total


def test_no_easyocr_or_torch_imports() -> None:
    """Solver module must not pull in easyocr / torch (size + supply chain)."""
    assert "easyocr" not in sys.modules
    assert "torch" not in sys.modules
    assert "torchvision" not in sys.modules


def test_solve_returns_none_on_bad_image() -> None:
    assert captcha.solve(b"not a jpeg") is None


def _fake_ddddocr_return(text: str, confidence: float) -> dict[str, object]:
    """Mirror the keys that ``captcha.solve()`` actually reads from ddddocr."""
    return {"text": text, "confidence": confidence}


def test_solve_returns_none_on_conf_below_threshold() -> None:
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = _fake_ddddocr_return("1234", 0.75)
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        assert captcha.solve(b"\xff\xd8\xffanything") is None


def test_solve_returns_none_on_wrong_length() -> None:
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = _fake_ddddocr_return("12345", 0.99)
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        assert captcha.solve(b"\xff\xd8\xffanything") is None


def test_solve_returns_none_on_non_digit_text() -> None:
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = _fake_ddddocr_return("12a4", 0.99)
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        assert captcha.solve(b"\xff\xd8\xffanything") is None


def test_solve_returns_result_on_passing_gate() -> None:
    mock_ocr = MagicMock()
    mock_ocr.classification.return_value = _fake_ddddocr_return("1234", 0.95)
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        result = captcha.solve(b"\xff\xd8\xffanything")
        assert result is not None
        assert result.text == "1234"
        assert result.confidence == pytest.approx(0.95)


def test_solve_returns_none_on_ocr_exception() -> None:
    mock_ocr = MagicMock()
    mock_ocr.classification.side_effect = RuntimeError("decode failed")
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        assert captcha.solve(b"\xff\xd8\xffanything") is None


def test_ocr_is_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_ocr must only instantiate DdddOcr once across calls."""
    monkeypatch.setattr(captcha, "_OCR", None)
    with patch("ccas.ingestor.fetcher.banks.fubon.captcha.ddddocr.DdddOcr") as mock_cls:
        mock_cls.return_value.classification.return_value = _fake_ddddocr_return(
            "0000", 0.1
        )
        captcha.solve(b"\xff\xd8\xffa")
        captcha.solve(b"\xff\xd8\xffb")
        assert mock_cls.call_count == 1


def test_solve_rejects_oversized_blob() -> None:
    """Byte-length guard: inputs > 512 KB are rejected before touching OCR."""
    oversized = b"\xff\xd8\xff" + b"\x00" * (600 * 1024)
    mock_ocr = MagicMock()
    with patch.object(captcha, "_get_ocr", return_value=mock_ocr):
        assert captcha.solve(oversized) is None
    mock_ocr.classification.assert_not_called()
