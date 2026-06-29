"""Unit tests for ``ccas.tools.categories``.

Covers YAML validation (``load_category_specs``), provenance-aware sync
(``apply_categories``), default-path / argparse plumbing, and the CLI
entrypoints (``_run_cli`` / ``main``).

Async tests use a self-contained in-memory SQLite engine (asyncio_mode=auto,
so no marker is required). The DB-backed CLI tests use a file-based SQLite so
the schema survives across the separate connections the CLI opens.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ccas.storage.models import Base, Category
from ccas.tools import categories as categories_mod
from ccas.tools.categories import (
    CategorySpec,
    CategorySyncSummary,
    CategoryValidationError,
    apply_categories,
    build_parser,
    load_category_specs,
    main,
)

BASE_YAML = """\
categories:
  - category: 餐飲
    keywords:
      - 麥當勞
      - 星巴克
  - category: 交通
    keywords:
      - 台灣高鐵
      - 悠遊卡
"""


@pytest.fixture
def write_yaml(tmp_path: Path) -> Callable[[str], Path]:
    def _write(content: str) -> Path:
        path = tmp_path / "categories.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


# ---------------------------------------------------------------------------
# load_category_specs
# ---------------------------------------------------------------------------


def test_load_specs_happy_path(write_yaml: Callable[[str], Path]) -> None:
    specs = load_category_specs(write_yaml(BASE_YAML))

    assert specs == [
        CategorySpec(keyword="麥當勞", category="餐飲"),
        CategorySpec(keyword="星巴克", category="餐飲"),
        CategorySpec(keyword="台灣高鐵", category="交通"),
        CategorySpec(keyword="悠遊卡", category="交通"),
    ]


def test_load_specs_accepts_path_as_str(write_yaml: Callable[[str], Path]) -> None:
    # Exercise the ``str`` branch of the ``str | Path`` parameter.
    specs = load_category_specs(str(write_yaml(BASE_YAML)))
    assert {s.keyword for s in specs} == {"麥當勞", "星巴克", "台灣高鐵", "悠遊卡"}


def test_load_specs_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(CategoryValidationError, match="找不到 categories.yaml"):
        load_category_specs(tmp_path / "missing.yaml")


def test_load_specs_invalid_yaml(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="不是合法 YAML"):
        load_category_specs(write_yaml("{[broken"))


def test_load_specs_non_dict_toplevel(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="頂層必須是物件"):
        load_category_specs(write_yaml("- a\n- b"))


def test_load_specs_missing_categories_key(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="非空的 categories 清單"):
        load_category_specs(write_yaml("other: 1"))


def test_load_specs_categories_not_a_list(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="非空的 categories 清單"):
        load_category_specs(write_yaml("categories: not-a-list"))


def test_load_specs_empty_categories(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="非空的 categories 清單"):
        load_category_specs(write_yaml("categories: []"))


def test_load_specs_non_dict_row(write_yaml: Callable[[str], Path]) -> None:
    with pytest.raises(CategoryValidationError, match="第 1 筆必須是物件"):
        load_category_specs(write_yaml("categories:\n  - just-a-string"))


def test_load_specs_missing_category_field(write_yaml: Callable[[str], Path]) -> None:
    yaml = "categories:\n  - keywords: [麥當勞]"
    with pytest.raises(CategoryValidationError, match="第 1 筆缺少 category"):
        load_category_specs(write_yaml(yaml))


def test_load_specs_blank_category_field(write_yaml: Callable[[str], Path]) -> None:
    yaml = 'categories:\n  - category: "   "\n    keywords: [麥當勞]'
    with pytest.raises(CategoryValidationError, match="第 1 筆缺少 category"):
        load_category_specs(write_yaml(yaml))


def test_load_specs_keywords_not_list(write_yaml: Callable[[str], Path]) -> None:
    yaml = "categories:\n  - category: 餐飲\n    keywords: 麥當勞"
    with pytest.raises(CategoryValidationError, match="keywords 必須是非空清單"):
        load_category_specs(write_yaml(yaml))


def test_load_specs_keywords_empty(write_yaml: Callable[[str], Path]) -> None:
    yaml = "categories:\n  - category: 餐飲\n    keywords: []"
    with pytest.raises(CategoryValidationError, match="keywords 必須是非空清單"):
        load_category_specs(write_yaml(yaml))


def test_load_specs_blank_keyword(write_yaml: Callable[[str], Path]) -> None:
    yaml = 'categories:\n  - category: 餐飲\n    keywords: ["  "]'
    with pytest.raises(CategoryValidationError, match="出現空白 keyword"):
        load_category_specs(write_yaml(yaml))


def test_load_specs_duplicate_keyword_same_category_deduped(
    write_yaml: Callable[[str], Path],
) -> None:
    yaml = "categories:\n  - category: 餐飲\n    keywords: [麥當勞, 麥當勞]"
    specs = load_category_specs(write_yaml(yaml))
    assert specs == [CategorySpec(keyword="麥當勞", category="餐飲")]


def test_load_specs_duplicate_keyword_conflicting_category(
    write_yaml: Callable[[str], Path],
) -> None:
    yaml = (
        "categories:\n"
        "  - category: 餐飲\n"
        "    keywords: [麥當勞]\n"
        "  - category: 速食\n"
        "    keywords: [麥當勞]\n"
    )
    with pytest.raises(CategoryValidationError, match="被對應到多個分類"):
        load_category_specs(write_yaml(yaml))


# ---------------------------------------------------------------------------
# apply_categories
# ---------------------------------------------------------------------------


async def test_apply_creates_rows_with_seed_source(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    specs = load_category_specs(write_yaml(BASE_YAML))

    summary = await apply_categories(session, specs, apply_changes=True)

    assert summary.created == 4
    assert summary.updated == 0
    assert summary.unchanged == 0
    assert summary.deleted == 0
    assert summary.skipped_user == 0
    assert all(a.startswith("CREATE") for a in summary.actions)

    rows = (await session.execute(select(Category))).scalars().all()
    assert {r.keyword for r in rows} == {"麥當勞", "星巴克", "台灣高鐵", "悠遊卡"}
    assert all(r.source == "seed" for r in rows)


async def test_apply_dry_run_does_not_persist(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    specs = load_category_specs(write_yaml(BASE_YAML))

    summary = await apply_categories(session, specs, apply_changes=False)

    assert summary.created == 4
    rows = (await session.execute(select(Category))).scalars().all()
    assert rows == []


async def test_apply_is_idempotent_unchanged(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    specs = load_category_specs(write_yaml(BASE_YAML))
    await apply_categories(session, specs, apply_changes=True)

    summary = await apply_categories(session, specs, apply_changes=True)

    assert summary.created == 0
    assert summary.unchanged == 4
    assert any(a.startswith("UNCHANGED") for a in summary.actions)


async def test_apply_updates_changed_seed_row(session: AsyncSession) -> None:
    session.add(Category(keyword="麥當勞", category="舊分類", source="seed"))
    await session.commit()

    specs = [CategorySpec(keyword="麥當勞", category="餐飲")]
    summary = await apply_categories(session, specs, apply_changes=True)

    assert summary.updated == 1
    assert summary.created == 0
    assert any("UPDATE 麥當勞" in a for a in summary.actions)

    row = (
        await session.execute(select(Category).where(Category.keyword == "麥當勞"))
    ).scalar_one()
    assert row.category == "餐飲"


async def test_apply_skips_user_override(session: AsyncSession) -> None:
    session.add(Category(keyword="麥當勞", category="自訂分類", source="user"))
    await session.commit()

    specs = [CategorySpec(keyword="麥當勞", category="餐飲")]
    summary = await apply_categories(session, specs, apply_changes=True)

    assert summary.skipped_user == 1
    assert summary.updated == 0
    assert any("SKIP user-override" in a for a in summary.actions)

    row = (
        await session.execute(select(Category).where(Category.keyword == "麥當勞"))
    ).scalar_one()
    assert row.category == "自訂分類"
    assert row.source == "user"


async def test_apply_deletes_orphan_seed_rows(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    await apply_categories(
        session, load_category_specs(write_yaml(BASE_YAML)), apply_changes=True
    )

    shrunk = "categories:\n  - category: 餐飲\n    keywords: [麥當勞]\n"
    summary = await apply_categories(
        session, load_category_specs(write_yaml(shrunk)), apply_changes=True
    )

    assert summary.deleted == 3
    assert summary.unchanged == 1
    assert any("DELETE orphan-seed" in a for a in summary.actions)

    result = await session.execute(select(Category))
    rows = {r.keyword for r in result.scalars().all()}
    assert rows == {"麥當勞"}


async def test_apply_never_deletes_user_orphans(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    await apply_categories(
        session, load_category_specs(write_yaml(BASE_YAML)), apply_changes=True
    )
    session.add(Category(keyword="自家手搖店", category="飲料", source="user"))
    await session.commit()

    shrunk = "categories:\n  - category: 餐飲\n    keywords: [麥當勞]\n"
    summary = await apply_categories(
        session, load_category_specs(write_yaml(shrunk)), apply_changes=True
    )

    # Only the three orphan SEED rows are deleted; the user row survives.
    assert summary.deleted == 3
    row = (
        await session.execute(select(Category).where(Category.keyword == "自家手搖店"))
    ).scalar_one_or_none()
    assert row is not None
    assert row.source == "user"


async def test_apply_dry_run_does_not_delete_orphans(
    session: AsyncSession, write_yaml: Callable[[str], Path]
) -> None:
    await apply_categories(
        session, load_category_specs(write_yaml(BASE_YAML)), apply_changes=True
    )

    shrunk = "categories:\n  - category: 餐飲\n    keywords: [麥當勞]\n"
    summary = await apply_categories(
        session, load_category_specs(write_yaml(shrunk)), apply_changes=False
    )

    assert summary.deleted == 3
    # Rollback path: nothing was actually removed.
    result = await session.execute(select(Category))
    rows = {r.keyword for r in result.scalars().all()}
    assert rows == {"麥當勞", "星巴克", "台灣高鐵", "悠遊卡"}


# ---------------------------------------------------------------------------
# build_parser / _default_config_path
# ---------------------------------------------------------------------------


def test_parser_default_uses_bank_config_dir_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")
    args = build_parser().parse_args([])
    assert args.config == "/config/categories.yaml"
    assert args.database_url == ""
    assert args.apply is False


def test_parser_default_falls_back_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BANK_CONFIG_DIR", raising=False)
    args = build_parser().parse_args([])
    assert args.config == "../config/categories.yaml"


def test_parser_explicit_flags_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")
    args = build_parser().parse_args(
        ["--config", "/tmp/custom.yaml", "--database-url", "sqlite://x", "--apply"]
    )
    assert args.config == "/tmp/custom.yaml"
    assert args.database_url == "sqlite://x"
    assert args.apply is True


# ---------------------------------------------------------------------------
# main / _run_cli
# ---------------------------------------------------------------------------


def test_main_returns_2_on_validation_error(
    write_yaml: Callable[[str], Path],
) -> None:
    bad = write_yaml("{[broken")
    assert main(["--config", str(bad)]) == 2


def test_main_database_url_dry_run(
    write_yaml: Callable[[str], Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--database-url`` branch + dry-run print path."""
    config = write_yaml(BASE_YAML)
    db_file = tmp_path / "cat.db"
    url = f"sqlite+aiosqlite:///{db_file}"

    # Pre-create the schema on the same file so the CLI's own connection
    # finds the categories table.
    import asyncio

    async def _create() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())

    rc = main(["--config", str(config), "--database-url", url])

    assert rc == 0
    out = capsys.readouterr().out
    assert "[DRY-RUN]" in out
    assert "created=4" in out
    assert "未寫入資料庫" in out
    assert "- CREATE 麥當勞 -> 餐飲" in out


def test_main_apply_uses_default_engine(
    write_yaml: Callable[[str], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No ``--database-url`` → falls back to get_engine/get_session_factory.

    Patch those so the CLI talks to a throwaway file-based SQLite instead of
    the real configured database, and verify --apply persists rows.
    """
    config = write_yaml(BASE_YAML)
    db_file = tmp_path / "default.db"
    url = f"sqlite+aiosqlite:///{db_file}"

    import asyncio

    async def _create() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())

    patched_engine = create_async_engine(url)
    factory = async_sessionmaker(
        patched_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(categories_mod, "get_engine", lambda: patched_engine)
    monkeypatch.setattr(categories_mod, "get_session_factory", lambda: factory)

    rc = main(["--config", str(config), "--apply"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "[APPLY]" in out
    assert "created=4" in out
    assert "未寫入資料庫" not in out

    async def _read() -> set[str]:
        engine = create_async_engine(url)
        read_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with read_factory() as s:
            rows = (await s.execute(select(Category))).scalars().all()
            keywords = {r.keyword for r in rows}
        await engine.dispose()
        return keywords

    assert asyncio.run(_read()) == {"麥當勞", "星巴克", "台灣高鐵", "悠遊卡"}


# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def test_summary_is_frozen() -> None:
    summary = CategorySyncSummary(
        created=1,
        updated=0,
        unchanged=0,
        deleted=0,
        skipped_user=0,
        actions=("CREATE x",),
    )
    with pytest.raises((AttributeError, TypeError)):
        summary.created = 9  # type: ignore[misc]
