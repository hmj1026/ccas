"""Unit tests for the FUBON captcha fixture evaluator."""

from __future__ import annotations

from pathlib import Path

from ccas.ingestor.fetcher.banks.fubon.captcha import CaptchaResult
from scripts import eval_captcha


def _write_fixtures(directory: Path, names: list[str]) -> None:
    for name in names:
        (directory / f"{name}.jpg").write_bytes(b"fixture")


def test_rejects_low_accept_rate_even_when_accepted_samples_are_correct(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fixtures(tmp_path, ["0000", "0001", "0002", "0003", "0004"])
    outcomes = iter(
        [CaptchaResult(text="0000", confidence=0.99), None, None, None, None]
    )
    monkeypatch.setattr(eval_captcha, "solve", lambda _: next(outcomes))

    assert eval_captcha.evaluate(tmp_path) == 1


def test_accept_rate_at_threshold_passes(monkeypatch, tmp_path: Path) -> None:
    _write_fixtures(tmp_path, ["0000", "0001", "0002", "0003", "0004"])
    outcomes = iter(
        [
            CaptchaResult(text="0000", confidence=0.99),
            CaptchaResult(text="0001", confidence=0.99),
            CaptchaResult(text="0002", confidence=0.99),
            CaptchaResult(text="0003", confidence=0.99),
            None,
        ]
    )
    monkeypatch.setattr(eval_captcha, "solve", lambda _: next(outcomes))

    assert eval_captcha.evaluate(tmp_path) == 0


def test_rejects_false_positive_even_when_rate_thresholds_pass(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fixtures(tmp_path, ["0000", "0001", "0002", "0003", "0004"])
    outcomes = iter(
        [
            CaptchaResult(text="0000", confidence=0.99),
            CaptchaResult(text="0001", confidence=0.99),
            CaptchaResult(text="0002", confidence=0.99),
            CaptchaResult(text="0003", confidence=0.99),
            CaptchaResult(text="9999", confidence=0.99),
        ]
    )
    monkeypatch.setattr(eval_captcha, "solve", lambda _: next(outcomes))

    assert eval_captcha.evaluate(tmp_path) == 1
