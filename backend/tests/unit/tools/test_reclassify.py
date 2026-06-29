"""Tests for ccas.tools.reclassify CLI."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import ccas.tools.reclassify as reclassify
from ccas.classifier.job import ClassifySummary


def test_main_runs_job_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main([]) wires the session factory, runs the job, disposes, and prints."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    summary = ClassifySummary(classified_count=5, skipped_count=2, total_count=7)
    job_mock = AsyncMock(return_value=summary)

    monkeypatch.setattr(reclassify, "get_session_factory", lambda: factory)
    monkeypatch.setattr(reclassify, "get_engine", lambda: engine)
    monkeypatch.setattr(reclassify, "run_reclassify_job", job_mock)

    reclassify.main([])

    out = capsys.readouterr().out
    assert "classified=5" in out
    assert "skipped=2" in out
    assert "total=7" in out
    job_mock.assert_awaited_once()


async def test_run_cli_passes_open_session_to_job(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """_run_cli opens a session from the factory and hands it to the job."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    captured: dict[str, object] = {}

    async def fake_job(session: AsyncSession) -> ClassifySummary:
        captured["session"] = session
        return ClassifySummary(classified_count=1, skipped_count=0, total_count=1)

    monkeypatch.setattr(reclassify, "get_session_factory", lambda: factory)
    monkeypatch.setattr(reclassify, "get_engine", lambda: engine)
    monkeypatch.setattr(reclassify, "run_reclassify_job", fake_job)

    await reclassify._run_cli()

    assert isinstance(captured["session"], AsyncSession)
    assert "classified=1" in capsys.readouterr().out
