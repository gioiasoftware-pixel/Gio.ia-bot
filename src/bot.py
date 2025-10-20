import os
import logging
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from .ai import get_ai_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
BOT_MODE = os.environ.get("BOT_MODE", "webhook")
PORT = int(os.environ.get("PORT", "8080"))  # Railway la setta in automatico


async def start_cmd(update, context):
    await update.message.reply_text("Ciao! Sono attivo 🚀")


async def help_cmd(update, context):
    await update.message.reply_text("Comandi: /start, /help")


async def chat_handler(update, context):
    user_text = update.message.text
    await update.message.reply_text("💭 Sto pensando...")
    reply = get_ai_response(user_text)
    await update.message.reply_text(reply)


async def healthcheck_handler(request: web.Request):
    logger.info("Healthcheck OK")
    return web.Response(text="OK", status=200)




def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    if BOT_MODE == "webhook":
        web_app = web.Application()
        web_app.router.add_get("/healthcheck", healthcheck_handler)

        logger.info(f"Starting webhook server on 0.0.0.0:{PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            webhook_path="/webhook",
            web_app=web_app,
        )
    else:
        logger.info("Starting bot in polling mode")
        app.run_polling()

if __name__ == "__main__":
    main()



