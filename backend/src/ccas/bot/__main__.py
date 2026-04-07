"""CLI 入口：python -m ccas.bot

啟動 Telegram Bot，使用長輪詢（polling）模式接收訊息。
"""

import logging
import sys

from ccas.config import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN 未設定，Bot 無法啟動")
        sys.exit(0)

    from ccas.bot.app import create_bot_app

    app = create_bot_app()
    app.run_polling()


if __name__ == "__main__":
    main()
