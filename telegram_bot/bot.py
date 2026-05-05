import sys
import os
import logging
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from backend.config import TELEGRAM_BOT_TOKEN
from backend.database import init_db
from telegram_bot.handlers import (
    cmd_start, cmd_analyse, cmd_news, cmd_risk,
    cmd_chat, cmd_alerte, cmd_status, cmd_patterns, cmd_sentiment,
    handle_signal_response,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN non configuré dans .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("analyse",   cmd_analyse))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("risk",      cmd_risk))
    app.add_handler(CommandHandler("chat",      cmd_chat))
    app.add_handler(CommandHandler("alerte",    cmd_alerte))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("patterns",  cmd_patterns))
    app.add_handler(CommandHandler("sentiment", cmd_sentiment))

    # OUI / NON responses to interactive signal alerts
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_signal_response))

    return app


def main():
    init_db()
    app = create_app()
    logger.info("Telegram bot démarré. En attente de messages...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
