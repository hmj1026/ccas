"""Pipeline API 觸發端點整合測試。

5.5: 驗證 API 端點能正確呼叫 run_pipeline() 並回傳摘要。
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth_headers


class TestPipelineTriggerEndpoint:
    """5.5: POST /api/pipeline/trigger 整合測試。"""

    @pytest.mark.asyncio
    async def test_trigger_returns_job_id(self, client: AsyncClient):
        """成功觸發 pipeline 應回傳 job ID。"""
        mock_job = MagicMock()
        mock_job.id = "test-job-123"

        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with (
            patch("ccas.api.routers.pipeline.Redis"),
            patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
        ):
            response = await client.post(
                "/api/pipeline/trigger",
                headers=auth_headers(),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["job_id"] == "test-job-123"

    @pytest.mark.asyncio
    async def test_trigger_requires_auth(self, client: AsyncClient):
        """無認證 token 應回傳 401 (HTTPBearer)。"""
        response = await client.post("/api/pipeline/trigger")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_rejects_invalid_token(self, client: AsyncClient):
        """錯誤 token 應回傳 401。"""
        response = await client.post(
            "/api/pipeline/trigger",
            headers=auth_headers("wrong-token"),
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_with_force_body(self, client: AsyncClient):
        """帶 force=true body 應成功觸發並傳遞 opts。"""
        mock_job = MagicMock()
        mock_job.id = "force-job-456"

        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with (
            patch("ccas.api.routers.pipeline.Redis"),
            patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
        ):
            response = await client.post(
                "/api/pipeline/trigger",
                headers=auth_headers(),
                json={"force": True, "bank_code": "CTBC"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["job_id"] == "force-job-456"

        # Verify opts dict was passed as first positional arg
        enqueue_call = mock_queue.enqueue.call_args
        opts_arg = enqueue_call[0][1]  # Second positional arg (after fn)
        assert opts_arg["force"] is True
        assert opts_arg["bank_code"] == "CTBC"

    @pytest.mark.asyncio
    async def test_trigger_with_empty_body(self, client: AsyncClient):
        """空 JSON body 應等同無 body，使用預設值。"""
        mock_job = MagicMock()
        mock_job.id = "default-job-789"

        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with (
            patch("ccas.api.routers.pipeline.Redis"),
            patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
        ):
            response = await client.post(
                "/api/pipeline/trigger",
                headers=auth_headers(),
                json={},
            )

        assert response.status_code == 200

        enqueue_call = mock_queue.enqueue.call_args
        opts_arg = enqueue_call[0][1]
        assert opts_arg["force"] is False
        assert opts_arg["bank_code"] is None

    @pytest.mark.asyncio
    async def test_trigger_invalid_month_returns_422(self, client: AsyncClient):
        """month 超出 1-12 範圍應回傳 422。"""
        mock_queue = MagicMock()

        with (
            patch("ccas.api.routers.pipeline.Redis"),
            patch("ccas.api.routers.pipeline.Queue", return_value=mock_queue),
        ):
            response = await client.post(
                "/api/pipeline/trigger",
                headers=auth_headers(),
                json={"month": 13},
            )

        assert response.status_code == 422
