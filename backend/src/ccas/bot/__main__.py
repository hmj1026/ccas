"""CLI 入口：python -m ccas.bot

啟動 Telegram Bot，使用長輪詢（polling）模式接收訊息。
"""

from ccas.bot.app import create_bot_app


def main() -> None:
    app = create_bot_app()
    app.run_polling()


if __name__ == "__main__":
    main()
