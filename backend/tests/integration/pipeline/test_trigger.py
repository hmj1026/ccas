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
