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




def _start_health_server(port: int) -> None:
    # Avvia un piccolo server HTTP in un thread separato sulla porta di Railway
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthcheck":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, format, *args):
            return  # silenzia il logging di BaseHTTPRequestHandler

    def serve():
        httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"Health server in ascolto su 0.0.0.0:{port}")
        httpd.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    # Su Railway usiamo polling + server HTTP per healthcheck sulla PORT
    use_polling_with_health = os.getenv("RAILWAY_ENVIRONMENT") is not None or BOT_MODE != "webhook"
    if use_polling_with_health:
        logger.info(f"Starting health server + polling on 0.0.0.0:{PORT}")
        # Avvia server health (thread daemon) e poi polling
        _start_health_server(PORT)
        # Avvia il polling (bloccante)
        app.run_polling()
        return

    # Modalità webhook classica (senza health server, non compatibile su PTB 21.5)
    logger.info("Starting bot in webhook mode (senza healthcheck HTTP)")
    app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    main()



