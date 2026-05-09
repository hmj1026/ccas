"""Seed bank_settings rows from banks.yaml（oauth-onboarding-ui §2.6）。

bank_settings 是「使用者偏好」表（enabled toggle / display_name / notes），
取代 banks.yaml 的 ``enabled`` 欄位作為 SSOT。entrypoint 啟動時呼叫此 seeder
以確保每個 yaml 中的銀行皆有預設 row（enabled=True）；既有 row 不覆寫
（INSERT OR IGNORE 語意），保留使用者透過 ``/setup/banks`` UI 做的修改。

設計取捨：本工具刻意不依賴 ``ccas.tools.bank_configs.load_bank_config_specs``，
因為後者強制驗證 bank-code-registry 與 gmail_filter；seed 階段只需要 bank_code
列表，避免任一驗證錯誤阻擋 entrypoint 啟動（fail-soft；entrypoint 段亦用
``||`` 包裹）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.database import get_engine, get_session_factory
from ccas.storage.models import BankSettings

logger = logging.getLogger(__name__)


async def seed_bank_settings_from_yaml(
    session: AsyncSession, yaml_path: str | Path
) -> int:
    """Insert default ``BankSettings`` rows for every bank_code in banks.yaml.

    Args:
        session: Async session bound to the target database.
        yaml_path: Path to ``banks.yaml``. Missing file returns 0.

    Returns:
        Number of newly inserted rows. Existing rows are NOT overwritten
        (preserving user toggle / display_name / notes).
    """
    path = Path(yaml_path)
    if not path.exists():
        logger.warning("banks.yaml not found at %s — skipping seed", path)
        return 0

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("banks.yaml parse failed: %s — skipping seed", exc)
        return 0

    if not isinstance(raw, dict):
        return 0
    rows = raw.get("banks")
    if not isinstance(rows, list):
        return 0

    yaml_entries: list[tuple[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("bank_code", "")).strip().upper()
        if not code:
            continue
        bank_name = row.get("bank_name")
        display_name = (
            str(bank_name).strip()
            if isinstance(bank_name, str) and bank_name.strip()
            else None
        )
        yaml_entries.append((code, display_name))

    if not yaml_entries:
        return 0

    existing = await session.execute(
        select(BankSettings.code).where(
            BankSettings.code.in_([c for c, _ in yaml_entries])
        )
    )
    existing_codes = {row[0] for row in existing.all()}

    inserted = 0
    for code, display_name in yaml_entries:
        if code in existing_codes:
            continue
        session.add(BankSettings(code=code, enabled=True, display_name=display_name))
        inserted += 1
    return inserted


def _resolve_default_yaml_path() -> Path:
    """Mirror the resolution used by ``ccas.tools.bank_configs``."""
    env_dir = os.environ.get("BANK_CONFIG_DIR")
    if env_dir:
        return Path(env_dir.rstrip("/")) / "banks.yaml"
    return Path("../config/banks.yaml")


async def _run_cli(yaml_path: Path, database_url: str | None) -> int:
    # Only dispose engines we own. ``get_engine()`` returns a process-wide
    # singleton; disposing it here would break subsequent callers.
    if database_url:
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        owns_engine = True
    else:
        engine = get_engine()
        factory = get_session_factory()
        owns_engine = False

    try:
        async with factory() as session:
            inserted = await seed_bank_settings_from_yaml(session, yaml_path)
            await session.commit()
    finally:
        if owns_engine:
            await engine.dispose()

    print(f"[seed_bank_settings] inserted={inserted} (source={yaml_path})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed bank_settings 預設 row（從 banks.yaml）。"
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "banks.yaml 路徑。未提供時：BANK_CONFIG_DIR/banks.yaml 或 "
            "../config/banks.yaml。"
        ),
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="覆寫資料庫連線字串；未提供時讀取 Settings。",
    )
    args = parser.parse_args(argv)
    yaml_path = Path(args.config) if args.config else _resolve_default_yaml_path()
    return asyncio.run(_run_cli(yaml_path, args.database_url))


if __name__ == "__main__":
    raise SystemExit(main())
