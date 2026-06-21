"""Telegram Bot 應用程式組裝。

建立 python-telegram-bot Application，註冊指令 handler，
並整合 chat_id 白名單驗證與 DB Session。
"""

import logging
from collections.abc import Callable
from functools import wraps

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from ccas.bot.auth import is_chat_allowed, load_allowed_chat_ids
from ccas.bot.handlers import (
    handle_category,
    handle_paid,
    handle_status,
    handle_summary,
    handle_upcoming,
)
from ccas.config import get_settings
from ccas.storage.database import get_session_factory

logger = logging.getLogger(__name__)


def _with_auth_and_session(
    handler_fn: Callable,
    allowed_chat_ids: frozenset[int],
    session_factory,
):
    """包裝 handler：先驗證白名單，再注入 DB Session。"""

    @wraps(handler_fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id if update.effective_chat else None
        # Authorization MUST stay OUTSIDE the try below so unauthorized chats
        # never receive an error reply (no information leak to non-allowlisted
        # users); they are silently ignored exactly as before.
        if chat_id is None or not is_chat_allowed(chat_id, allowed_chat_ids):
            return  # silently ignore

        try:
            async with session_factory() as session:
                await handler_fn(update, context, session)
        except Exception:
            # DB / Telegram errors must not leave the user with no feedback.
            logger.exception("Bot handler error in %s", handler_fn.__name__)
            # Replying can itself fail (Telegram API down); a failed error
            # reply only warns — never re-raise into the framework.
            if update.message is not None:
                try:
                    await update.message.reply_text("發生錯誤，請稍後再試。")
                except Exception:
                    logger.warning(
                        "Bot error reply failed in %s",
                        handler_fn.__name__,
                        exc_info=True,
                    )

    return wrapper


def create_bot_app() -> Application:
    """建立並設定 Telegram Bot Application。

    Returns:
        已註冊所有指令 handler 的 Application 實例。
    """
    settings = get_settings()
    allowed = load_allowed_chat_ids(settings.telegram_allowed_chat_ids)
    if not allowed:
        logger.warning(
            "TELEGRAM_ALLOWED_CHAT_IDS 未設定或為空，bot 指令對所有人停用(含擁有者)；"
            "請設定後重啟"
        )
    sf = get_session_factory()

    app = Application.builder().token(settings.telegram_bot_token).build()

    commands = {
        "status": handle_status,
        "upcoming": handle_upcoming,
        "summary": handle_summary,
        "category": handle_category,
        "paid": handle_paid,
    }

    for name, handler_fn in commands.items():
        wrapped = _with_auth_and_session(handler_fn, allowed, sf)
        app.add_handler(CommandHandler(name, wrapped))

    logger.info(
        "Bot configured with %d allowed chat_ids, %d commands",
        len(allowed),
        len(commands),
    )
    return app
