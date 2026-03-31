"""Gmail API retry 行為的單元測試。"""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from ccas.ingestor.retry import call_with_retry


def _make_http_error(status: int) -> HttpError:
    """建立指定 HTTP status 的 HttpError。"""
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


class TestCallWithRetry:
    """call_with_retry() 的測試案例。"""

    def test_success_on_first_attempt(self):
        """第一次就成功，只呼叫一次。"""
        fn = MagicMock(return_value="ok")
        result = call_with_retry(fn)
        assert result == "ok"
        assert fn.call_count == 1

    @patch("ccas.ingestor.retry.time.sleep")
    def test_retries_on_429(self, mock_sleep):
        """429 rate limit 時重試，第二次成功。"""
        fn = MagicMock(side_effect=[_make_http_error(429), "ok"])
        result = call_with_retry(fn)
        assert result == "ok"
        assert fn.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("ccas.ingestor.retry.time.sleep")
    def test_retries_on_5xx(self, mock_sleep):
        """5xx 錯誤時持續重試，用盡後拋出。"""
        fn = MagicMock(
            side_effect=[
                _make_http_error(500),
                _make_http_error(502),
                _make_http_error(503),
            ]
        )
        with pytest.raises(HttpError):
            call_with_retry(fn)
        assert fn.call_count == 3

    def test_no_retry_on_403(self):
        """非暫時性錯誤（403）不重試，直接拋出。"""
        fn = MagicMock(side_effect=_make_http_error(403))
        with pytest.raises(HttpError):
            call_with_retry(fn)
        assert fn.call_count == 1

    def test_no_retry_on_404(self):
        """非暫時性錯誤（404）不重試，直接拋出。"""
        fn = MagicMock(side_effect=_make_http_error(404))
        with pytest.raises(HttpError):
            call_with_retry(fn)
        assert fn.call_count == 1

    @patch("ccas.ingestor.retry.time.sleep")
    def test_backoff_sequence(self, mock_sleep):
        """驗證 backoff 間隔序列為 1s, 2s。"""
        fn = MagicMock(
            side_effect=[_make_http_error(429), _make_http_error(429), "ok"]
        )
        result = call_with_retry(fn)
        assert result == "ok"
        assert mock_sleep.call_args_list == [
            ((1,),),
            ((2,),),
        ]
