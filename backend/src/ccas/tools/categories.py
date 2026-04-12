"""Sync classification keyword categories from YAML to the database.

Default YAML path priority (same pattern as `ccas.tools.bank_configs`):

1. CLI `--config` flag (explicit) wins.
2. `BANK_CONFIG_DIR` environment variable → `{BANK_CONFIG_DIR}/categories.yaml`.
3. Hard-coded fallback `../config/categories.yaml` (host `scripts/setup.sh` flow).

Sync strategy (provenance-aware diff):

Rows carry a ``source`` column distinguishing ``"seed"`` (written by this
tool) from ``"user"`` (created or edited through the backend UI). The
reseed pass honours that distinction:

- keyword ∈ YAML and ∉ DB → INSERT with ``source="seed"`` (created).
- keyword ∈ YAML, ∈ DB, source=``seed``, category differs → UPDATE.
- keyword ∈ YAML, ∈ DB, source=``seed``, category same → unchanged.
- keyword ∈ YAML, ∈ DB, source=``user`` → skipped_user (user override wins).
- keyword ∉ YAML, ∈ DB, source=``seed`` → DELETE (YAML rollback takes
  effect instead of leaving stale seed rules behind).
- keyword ∉ YAML, ∈ DB, source=``user`` → left alone (user-added rows).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ccas.storage.database import get_engine, get_session_factory
from ccas.storage.models import Category
from ccas.tools.bank_configs import resolve_default_config_path


class CategoryValidationError(ValueError):
    """categories.yaml validation failure."""


@dataclass(frozen=True)
class CategorySpec:
    """A single (keyword, category) mapping parsed from YAML."""

    keyword: str
    category: str


@dataclass(frozen=True)
class CategorySyncSummary:
    created: int
    updated: int
    unchanged: int
    deleted: int
    skipped_user: int
    actions: tuple[str, ...]


def load_category_specs(path: str | Path) -> list[CategorySpec]:
    """Parse and validate categories.yaml."""
    yaml_path = Path(path)
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CategoryValidationError(
            f"找不到 categories.yaml: {yaml_path}。請先建立檔案再重試。"
        ) from None
    except yaml.YAMLError as exc:
        raise CategoryValidationError(
            f"categories.yaml 不是合法 YAML：{exc}。請修正縮排或冒號後再重試。"
        ) from exc

    if not isinstance(raw, dict):
        raise CategoryValidationError("categories.yaml 頂層必須是物件。")

    rows = raw.get("categories")
    if not isinstance(rows, list) or not rows:
        raise CategoryValidationError(
            "categories.yaml 必須包含非空的 categories 清單。"
        )

    specs: list[CategorySpec] = []
    seen: dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise CategoryValidationError(f"categories.yaml 第 {index} 筆必須是物件。")
        category = str(row.get("category", "")).strip()
        if not category:
            raise CategoryValidationError(
                f"categories.yaml 第 {index} 筆缺少 category。"
            )
        keywords = row.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise CategoryValidationError(
                f"categories.yaml 第 {index} 筆 ({category})"
                " 的 keywords 必須是非空清單。"
            )
        for keyword in keywords:
            text = str(keyword).strip()
            if not text:
                raise CategoryValidationError(
                    f"categories.yaml 第 {index} 筆 ({category}) 出現空白 keyword。"
                )
            existing_category = seen.get(text)
            if existing_category is not None:
                if existing_category != category:
                    raise CategoryValidationError(
                        f"categories.yaml 的 keyword '{text}' 被對應到多個分類："
                        f"{existing_category} 與 {category}。請保留一組並重試。"
                    )
                continue
            seen[text] = category
            specs.append(CategorySpec(keyword=text, category=category))

    return specs


async def apply_categories(
    session: AsyncSession,
    specs: list[CategorySpec],
    *,
    apply_changes: bool,
) -> CategorySyncSummary:
    """Diff YAML specs against the categories table and sync.

    Provenance-aware: seed rows (``source="seed"``) are fully managed by
    this tool and can be deleted when removed from YAML; user rows
    (``source="user"``) are never overwritten or deleted.
    """
    result = await session.execute(select(Category))
    existing = {row.keyword: row for row in result.scalars().all()}

    created = 0
    updated = 0
    unchanged = 0
    deleted = 0
    skipped_user = 0
    actions: list[str] = []

    yaml_keywords = {spec.keyword for spec in specs}

    for spec in specs:
        row = existing.get(spec.keyword)
        if row is None:
            created += 1
            actions.append(f"CREATE {spec.keyword} -> {spec.category}")
            if apply_changes:
                session.add(
                    Category(
                        keyword=spec.keyword,
                        category=spec.category,
                        source="seed",
                    )
                )
            continue

        if row.source == "user":
            # User-managed row wins: do not touch category even if YAML
            # disagrees. Flagged in the summary so operators know a YAML
            # change did not propagate.
            skipped_user += 1
            actions.append(
                f"SKIP user-override {spec.keyword} (keeps {row.category!r})"
            )
            continue

        if row.category == spec.category:
            unchanged += 1
            actions.append(f"UNCHANGED {spec.keyword}")
            continue

        updated += 1
        actions.append(f"UPDATE {spec.keyword}: {row.category} -> {spec.category}")
        if apply_changes:
            row.category = spec.category

    # Delete seed rows that are no longer present in YAML. User rows are
    # never touched here — that is the whole point of the provenance field.
    orphan_ids: list[int] = []
    for keyword, row in existing.items():
        if keyword in yaml_keywords:
            continue
        if row.source != "seed":
            continue
        deleted += 1
        actions.append(f"DELETE orphan-seed {keyword} (was {row.category!r})")
        orphan_ids.append(row.id)

    if apply_changes and orphan_ids:
        await session.execute(delete(Category).where(Category.id.in_(orphan_ids)))

    if apply_changes:
        await session.commit()
    else:
        await session.rollback()

    return CategorySyncSummary(
        created=created,
        updated=updated,
        unchanged=unchanged,
        deleted=deleted,
        skipped_user=skipped_user,
        actions=tuple(actions),
    )


_FALLBACK_CONFIG_PATH = "../config/categories.yaml"


def _default_config_path() -> str:
    return resolve_default_config_path("categories.yaml", _FALLBACK_CONFIG_PATH)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="將本地 categories.yaml 同步到 categories 資料表。"
    )
    parser.add_argument(
        "--config",
        default=_default_config_path(),
        help=(
            "categories.yaml 路徑。優先序：此 flag > `BANK_CONFIG_DIR` 環境變數 > "
            "`../config/categories.yaml` 預設值。"
        ),
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


async def _run_cli(args: argparse.Namespace) -> int:
    specs = load_category_specs(args.config)
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
            summary = await apply_categories(session, specs, apply_changes=args.apply)
    finally:
        await engine.dispose()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] created={summary.created}"
        f" updated={summary.updated}"
        f" unchanged={summary.unchanged}"
        f" deleted={summary.deleted}"
        f" skipped_user={summary.skipped_user}"
    )
    for action in summary.actions:
        print(f"- {action}")
    if not args.apply:
        print("未寫入資料庫。若內容正確，請改用 --apply。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_cli(args))
    except CategoryValidationError as exc:
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
