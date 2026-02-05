from __future__ import annotations

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_IDS, BOT_TOKEN
from db import init_db
from handlers import admin, common, user
from logging_conf import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> None:
    setup_logging()

    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN .env faylida yo'q.")
    if not ADMIN_IDS:
        logger.warning("⚠️ ADMIN_IDS .env faylida yo'q. Hech kim admin bo'lmaydi!")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", user.start))
    app.add_handler(CommandHandler("admin", admin.admin_command))
    app.add_handler(CommandHandler("rand", user.random_movies))
    app.add_handler(CallbackQueryHandler(admin.callbacks))
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.PHOTO | filters.Document.ALL,
            admin.handle_admin_media,
            block=False,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            admin.handle_admin_text,
        )
    )
    app.add_handler(MessageHandler(filters.ALL, common.handle_other_messages))

    logger.info("🚀 Bot ishga tushdi...")
    logger.info("👥 Adminlar: %s", ADMIN_IDS)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
