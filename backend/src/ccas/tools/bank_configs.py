"""從本地 YAML 同步銀行設定到資料庫。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.database import get_engine, get_session_factory
from ccas.storage.models import BankConfig


class BankConfigValidationError(ValueError):
    """銀行設定 YAML 驗證失敗。"""


DEFAULT_PARSER_VERSION = "v1"


@dataclass(frozen=True)
class BankRegistryEntry:
    """bank_code registry 項目。"""

    bank_code: str
    bank_name: str
    fsc_code: str
    supported: bool = False
    notes: str = ""


@dataclass(frozen=True)
class BankConfigSpec:
    """YAML 解析後的銀行設定。"""

    bank_code: str
    bank_name: str
    gmail_filter: str
    active_parser_version: str = DEFAULT_PARSER_VERSION
    is_active: bool = True


@dataclass(frozen=True)
class SyncSummary:
    """同步摘要。"""

    created: int
    updated: int
    unchanged: int
    actions: tuple[str, ...]


def load_bank_registry(path: str | Path) -> dict[str, BankRegistryEntry]:
    """載入正式 bank_code registry。"""
    data = _load_yaml_mapping(Path(path), label="bank-code-registry.yaml")
    rows = data.get("banks")
    if not isinstance(rows, list) or not rows:
        raise BankConfigValidationError(
            "bank-code-registry.yaml 必須包含非空的 banks 清單。"
        )

    registry: dict[str, BankRegistryEntry] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise BankConfigValidationError(
                f"bank-code-registry.yaml 第 {index} 筆必須是物件。"
            )
        raw_code = str(row.get("bank_code", "")).strip().upper()
        raw_name = str(row.get("bank_name", "")).strip()
        if not raw_code or not raw_name:
            raise BankConfigValidationError(
                f"bank-code-registry.yaml 第 {index} 筆缺少 bank_code 或 bank_name。"
            )
        raw_fsc = str(row.get("fsc_code", "")).strip()
        if not raw_fsc or len(raw_fsc) != 3 or not raw_fsc.isdigit():
            raise BankConfigValidationError(
                f"bank-code-registry.yaml 第 {index} 筆 ({raw_code}) "
                f"的 fsc_code 必須是三位數字字串，實際值: {raw_fsc!r}"
            )
        if raw_code in registry:
            raise BankConfigValidationError(
                f"bank-code-registry.yaml 出現重複 bank_code: {raw_code}"
            )
        registry[raw_code] = BankRegistryEntry(
            bank_code=raw_code,
            bank_name=raw_name,
            fsc_code=raw_fsc,
            supported=bool(row.get("supported", False)),
            notes=str(row.get("notes", "")).strip(),
        )
    return registry


def load_bank_config_specs(
    config_path: str | Path, registry_path: str | Path
) -> list[BankConfigSpec]:
    """載入並驗證 banks.yaml。"""
    registry = load_bank_registry(registry_path)
    data = _load_yaml_mapping(Path(config_path), label="banks.yaml")
    rows = data.get("banks")
    if not isinstance(rows, list) or not rows:
        raise BankConfigValidationError("banks.yaml 必須包含非空的 banks 清單。")

    specs: list[BankConfigSpec] = []
    seen_codes: set[str] = set()

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise BankConfigValidationError(f"banks.yaml 第 {index} 筆必須是物件。")

        bank_code = str(row.get("bank_code", "")).strip().upper()
        if not bank_code:
            raise BankConfigValidationError(
                f"banks.yaml 第 {index} 筆缺少 bank_code。"
                "請改用 registry 中定義的代碼。"
            )
        if bank_code in seen_codes:
            raise BankConfigValidationError(
                f"banks.yaml 出現重複 bank_code: {bank_code}。請保留一筆並重試。"
            )
        if bank_code not in registry:
            allowed = ", ".join(sorted(registry))
            raise BankConfigValidationError(
                f"banks.yaml 使用了未知的 bank_code: {bank_code}。"
                f"請先查看 bank-code-registry.yaml，可用值：{allowed}"
            )

        gmail_filter = str(row.get("gmail_filter", "")).strip()
        if not gmail_filter:
            raise BankConfigValidationError(
                f"banks.yaml 第 {index} 筆 ({bank_code}) 缺少 gmail_filter。"
                "請填入能在 Gmail 搜到帳單的搜尋條件。"
            )

        active_parser_version = (
            str(row.get("active_parser_version", DEFAULT_PARSER_VERSION)).strip()
            or DEFAULT_PARSER_VERSION
        )
        is_active = bool(row.get("is_active", True))

        seen_codes.add(bank_code)
        specs.append(
            BankConfigSpec(
                bank_code=bank_code,
                bank_name=registry[bank_code].bank_name,
                gmail_filter=gmail_filter,
                active_parser_version=active_parser_version,
                is_active=is_active,
            )
        )

    return specs


async def sync_bank_configs(
    session: AsyncSession,
    specs: list[BankConfigSpec],
    *,
    apply_changes: bool,
) -> SyncSummary:
    """把 YAML 設定同步到資料庫。"""
    result = await session.execute(select(BankConfig))
    existing_rows = {row.bank_code.upper(): row for row in result.scalars().all()}

    created = 0
    updated = 0
    unchanged = 0
    actions: list[str] = []

    for spec in specs:
        row = existing_rows.get(spec.bank_code)
        if row is None:
            created += 1
            actions.append(f"CREATE {spec.bank_code}: gmail_filter={spec.gmail_filter}")
            if apply_changes:
                session.add(
                    BankConfig(
                        bank_code=spec.bank_code,
                        bank_name=spec.bank_name,
                        gmail_filter=spec.gmail_filter,
                        active_parser_version=spec.active_parser_version,
                        is_active=spec.is_active,
                    )
                )
            continue

        changed = (
            row.bank_name != spec.bank_name
            or row.gmail_filter != spec.gmail_filter
            or row.active_parser_version != spec.active_parser_version
            or row.is_active != spec.is_active
        )
        if not changed:
            unchanged += 1
            actions.append(f"UNCHANGED {spec.bank_code}")
            continue

        updated += 1
        actions.append(f"UPDATE {spec.bank_code}")
        if apply_changes:
            row.bank_name = spec.bank_name
            row.gmail_filter = spec.gmail_filter
            row.active_parser_version = spec.active_parser_version
            row.is_active = spec.is_active

    if apply_changes:
        await session.commit()
    else:
        await session.rollback()

    return SyncSummary(
        created=created,
        updated=updated,
        unchanged=unchanged,
        actions=tuple(actions),
    )


def _load_yaml_mapping(path: Path, *, label: str) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BankConfigValidationError(f"找不到 {label}: {path}。請先建立檔案再重試。")
    except yaml.YAMLError as exc:
        raise BankConfigValidationError(
            f"{label} 不是合法 YAML：{exc}。請修正縮排或冒號後再重試。"
        ) from exc
    if not isinstance(raw, dict):
        raise BankConfigValidationError(f"{label} 頂層必須是物件。")
    return raw


async def _run_cli(args: argparse.Namespace) -> int:
    specs = load_bank_config_specs(args.config, args.registry)
    if args.database_url:
        engine = create_async_engine(args.database_url)
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    else:
        engine = get_engine()
        session_factory = get_session_factory()

    try:
        async with session_factory() as session:
            summary = await sync_bank_configs(session, specs, apply_changes=args.apply)
    finally:
        await engine.dispose()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] created={summary.created}"
        f" updated={summary.updated}"
        f" unchanged={summary.unchanged}"
    )
    for action in summary.actions:
        print(f"- {action}")
    if not args.apply:
        print("未寫入資料庫。若內容正確，請改用 --apply。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="將本地 banks.yaml 同步到 bank_configs 資料表。"
    )
    parser.add_argument(
        "--config",
        default="../config/banks.yaml",
        help="banks.yaml 路徑",
    )
    parser.add_argument(
        "--registry",
        default="../config/bank-code-registry.yaml",
        help="bank_code registry 路徑",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="覆寫資料庫連線字串；未提供時讀取 Settings。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真的寫入資料庫；未提供時只做 dry-run。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_cli(args))
    except BankConfigValidationError as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
