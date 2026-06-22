"""Bot CLI 入口日誌初始化測試（roadmap: logging-init-pipeline-bot）。"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from ccas.bot.__main__ import main


class TestMainConfiguresLogging:
    def test_main_configures_logging_before_token_warning(self):
        """缺少 token 時，warning 前必須先完成 configure_logging(settings)。"""
        settings = MagicMock(telegram_bot_token=SecretStr(""))

        with (
            patch("ccas.bot.__main__.get_settings", return_value=settings),
            patch("ccas.bot.__main__.configure_logging") as mock_configure,
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        mock_configure.assert_called_once_with(settings)

    def test_main_configures_logging_then_starts_polling(self):
        """token 存在時，configure_logging 後啟動 polling。"""
        settings = MagicMock(telegram_bot_token=SecretStr("test-token"))
        bot_app = MagicMock()

        with (
            patch("ccas.bot.__main__.get_settings", return_value=settings),
            patch("ccas.bot.__main__.configure_logging") as mock_configure,
            patch("ccas.bot.app.create_bot_app", return_value=bot_app),
        ):
            main()

        mock_configure.assert_called_once_with(settings)
        bot_app.run_polling.assert_called_once()
