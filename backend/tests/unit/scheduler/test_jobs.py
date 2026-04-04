"""trigger_pipeline_via_api() 測試。

驗證 URL 建構、認證 header、以及錯誤傳播行為。
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ccas.scheduler.jobs import trigger_pipeline_via_api


class TestTriggerPipelineUrl:
    """URL 建構邏輯的測試案例。"""

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_uses_scheduler_api_base_url_when_set(self, mock_settings, mock_post):
        """scheduler_api_base_url 有值時，使用該值建構 URL。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = "http://backend:8000"
        settings.api_token = "test-token"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        trigger_pipeline_via_api()

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url == "http://backend:8000/api/pipeline/trigger"

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_fallback_uses_loopback_not_bind_address(self, mock_settings, mock_post):
        """scheduler_api_base_url 為空時，fallback 到 127.0.0.1:api_port。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = ""
        settings.api_host = "0.0.0.0"
        settings.api_port = 8000
        settings.api_token = "test-token"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        trigger_pipeline_via_api()

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url == "http://127.0.0.1:8000/api/pipeline/trigger"

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_strips_trailing_slash_from_base_url(self, mock_settings, mock_post):
        """base_url 尾端的斜線應被移除，避免雙斜線。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = "http://backend:8000/"
        settings.api_token = "test-token"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        trigger_pipeline_via_api()

        call_url = mock_post.call_args[0][0]
        assert call_url == "http://backend:8000/api/pipeline/trigger"


class TestTriggerPipelineErrorHandling:
    """錯誤傳播與認證 header 的測試案例。"""

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_trigger_failure_propagates(self, mock_settings, mock_post):
        """API 呼叫失敗時，例外應傳播給呼叫端。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = "http://backend:8000"
        settings.api_token = "test-token"
        mock_settings.return_value = settings

        mock_post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(httpx.ConnectError):
            trigger_pipeline_via_api()

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_trigger_sends_auth_header(self, mock_settings, mock_post):
        """應以 Bearer token 送出 Authorization header。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = "http://backend:8000"
        settings.api_token = "my-secret-token"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        trigger_pipeline_via_api()

        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["headers"] == {
            "Authorization": "Bearer my-secret-token",
        }

    @patch("ccas.scheduler.jobs.httpx.post")
    @patch("ccas.scheduler.jobs.get_settings")
    def test_http_error_propagates(self, mock_settings, mock_post):
        """HTTP 4xx/5xx 錯誤應傳播。"""
        settings = MagicMock()
        settings.scheduler_api_base_url = "http://backend:8000"
        settings.api_token = "test-token"
        mock_settings.return_value = settings

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        mock_post.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            trigger_pipeline_via_api()
