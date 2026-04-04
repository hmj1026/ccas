"""trigger_pipeline_via_api() URL 建構測試。

驗證 scheduler_api_base_url 有值時優先使用，空值時 fallback。
"""

from unittest.mock import MagicMock, patch

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
    def test_fallback_to_api_host_when_empty(self, mock_settings, mock_post):
        """scheduler_api_base_url 為空時，fallback 到 api_host:api_port。"""
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
        assert call_url == "http://0.0.0.0:8000/api/pipeline/trigger"

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
