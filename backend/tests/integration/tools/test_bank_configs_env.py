"""`BANK_CONFIG_DIR` env var 優先序測試（change: fix-docker-bank-configs-seed）。

三層優先序驗證：explicit flag > `BANK_CONFIG_DIR` env > hard-coded `../config/...`。
"""

from __future__ import annotations

import pytest

from ccas.tools.bank_configs import build_parser


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BANK_CONFIG_DIR", raising=False)


def test_defaults_fall_back_to_relative_config_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env 未設時，`--config` / `--registry` default 應退回 `../config/...`。"""
    monkeypatch.delenv("BANK_CONFIG_DIR", raising=False)

    parser = build_parser()
    args = parser.parse_args([])

    assert args.config == "../config/banks.yaml"
    assert args.registry == "../config/bank-code-registry.yaml"


def test_env_var_overrides_hardcoded_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """設定 `BANK_CONFIG_DIR=/config` 時 default 應指向該目錄下的 YAML。"""
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")

    parser = build_parser()
    args = parser.parse_args([])

    assert args.config == "/config/banks.yaml"
    assert args.registry == "/config/bank-code-registry.yaml"


def test_explicit_flag_overrides_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """即使 env 已設，explicit `--config` / `--registry` 仍應勝出。"""
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")

    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            "/tmp/custom-banks.yaml",
            "--registry",
            "/tmp/custom-registry.yaml",
        ]
    )

    assert args.config == "/tmp/custom-banks.yaml"
    assert args.registry == "/tmp/custom-registry.yaml"


def test_env_var_with_trailing_slash_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/config/` 尾端斜線不應產生 `/config//banks.yaml`。"""
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config/")

    parser = build_parser()
    args = parser.parse_args([])

    assert args.config == "/config/banks.yaml"
    assert args.registry == "/config/bank-code-registry.yaml"
