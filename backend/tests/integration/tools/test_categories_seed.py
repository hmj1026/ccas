"""Tests for ccas.tools.categories seed CLI (Change #3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from ccas.storage.models import Category
from ccas.tools.categories import apply_categories, build_parser, load_category_specs


@pytest.fixture
def yaml_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def write_yaml(yaml_dir: Path):
    def _write(content: str) -> Path:
        path = yaml_dir / "categories.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    return _write


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


async def test_apply_to_empty_table_creates_all(db_session, write_yaml) -> None:
    path = write_yaml(BASE_YAML)
    specs = load_category_specs(path)

    summary = await apply_categories(db_session, specs, apply_changes=True)

    assert summary.created == 4
    assert summary.updated == 0
    assert summary.unchanged == 0

    result = await db_session.execute(select(Category))
    rows = result.scalars().all()
    assert {r.keyword for r in rows} == {"麥當勞", "星巴克", "台灣高鐵", "悠遊卡"}
    assert next(r.category for r in rows if r.keyword == "麥當勞") == "餐飲"


async def test_reapply_is_idempotent(db_session, write_yaml) -> None:
    path = write_yaml(BASE_YAML)
    specs = load_category_specs(path)

    await apply_categories(db_session, specs, apply_changes=True)
    summary = await apply_categories(db_session, specs, apply_changes=True)

    assert summary.created == 0
    assert summary.updated == 0
    assert summary.unchanged == 4


async def test_changed_category_triggers_update(db_session, write_yaml) -> None:
    path = write_yaml(BASE_YAML)
    await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    modified = """\
categories:
  - category: 速食
    keywords:
      - 麥當勞
  - category: 餐飲
    keywords:
      - 星巴克
  - category: 交通
    keywords:
      - 台灣高鐵
      - 悠遊卡
"""
    path.write_text(modified, encoding="utf-8")

    summary = await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    assert summary.updated == 1
    assert summary.created == 0

    result = await db_session.execute(
        select(Category).where(Category.keyword == "麥當勞")
    )
    row = result.scalar_one()
    assert row.category == "速食"


async def test_user_added_rows_are_preserved(db_session, write_yaml) -> None:
    path = write_yaml(BASE_YAML)
    db_session.add(Category(keyword="自家手搖店", category="飲料"))
    await db_session.commit()

    summary = await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    assert summary.created == 4

    result = await db_session.execute(
        select(Category).where(Category.keyword == "自家手搖店")
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.category == "飲料"


async def test_reseed_deletes_yaml_removed_seed_rows(db_session, write_yaml) -> None:
    """Keywords removed from YAML must be deleted from the categories table
    on reseed. Without provenance tracking this rollback was impossible and
    stale rules stayed in the DB forever."""
    path = write_yaml(BASE_YAML)
    await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    shrunk = """\
categories:
  - category: 餐飲
    keywords:
      - 麥當勞
  - category: 交通
    keywords:
      - 台灣高鐵
"""
    path.write_text(shrunk, encoding="utf-8")

    summary = await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    assert summary.deleted == 2
    assert summary.unchanged == 2

    result = await db_session.execute(select(Category))
    rows = {r.keyword for r in result.scalars().all()}
    assert rows == {"麥當勞", "台灣高鐵"}


async def test_reseed_preserves_user_added_rows(db_session, write_yaml) -> None:
    """User-created rows (source='user') must survive reseed even when their
    keyword does not appear in YAML — the delete pass only targets seed rows."""
    path = write_yaml(BASE_YAML)
    await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )
    db_session.add(
        Category(keyword="自家手搖店", category="飲料", source="user")
    )
    await db_session.commit()

    shrunk = """\
categories:
  - category: 餐飲
    keywords:
      - 麥當勞
"""
    path.write_text(shrunk, encoding="utf-8")
    summary = await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    assert summary.deleted == 3  # 星巴克, 台灣高鐵, 悠遊卡 (seed rows only)
    result = await db_session.execute(
        select(Category).where(Category.keyword == "自家手搖店")
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.source == "user"


async def test_reseed_skips_user_overrides(db_session, write_yaml) -> None:
    """If a user has re-mapped a keyword manually (source='user'), a later
    YAML change must not silently overwrite their choice — record as
    skipped_user instead."""
    path = write_yaml(BASE_YAML)
    db_session.add(
        Category(keyword="麥當勞", category="自訂分類", source="user")
    )
    await db_session.commit()

    summary = await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )

    assert summary.skipped_user == 1
    result = await db_session.execute(
        select(Category).where(Category.keyword == "麥當勞")
    )
    row = result.scalar_one()
    assert row.category == "自訂分類"
    assert row.source == "user"


async def test_new_seed_inserts_carry_source_seed(db_session, write_yaml) -> None:
    path = write_yaml(BASE_YAML)
    await apply_categories(
        db_session, load_category_specs(path), apply_changes=True
    )
    result = await db_session.execute(select(Category))
    for row in result.scalars().all():
        assert row.source == "seed"


def test_default_config_path_uses_bank_config_dir_env(monkeypatch) -> None:
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")
    parser = build_parser()
    args = parser.parse_args([])
    assert args.config == "/config/categories.yaml"


def test_default_config_path_falls_back_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("BANK_CONFIG_DIR", raising=False)
    parser = build_parser()
    args = parser.parse_args([])
    assert args.config == "../config/categories.yaml"


def test_explicit_flag_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("BANK_CONFIG_DIR", "/config")
    parser = build_parser()
    args = parser.parse_args(["--config", "/tmp/custom.yaml"])
    assert args.config == "/tmp/custom.yaml"
