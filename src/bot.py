import os
import logging
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from .ai import get_ai_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carica variabili ambiente direttamente (senza validazione complessa)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
BOT_MODE = os.getenv("BOT_MODE", "webhook")
PORT = int(os.getenv("PORT", "8080"))  # Railway la setta in automatico

# Validazione base
if not TELEGRAM_BOT_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN non configurato!")
    exit(1)


async def start_cmd(update, context):
    user = update.effective_user
    username = user.username or user.first_name or "Utente"
    logger.info(f"Nuovo utente: {username} (ID: {user.id})")
    
    welcome_text = (
        f"Ciao {username}! 👋\n\n"
        "🤖 Sono **Gio.ia-bot**, il tuo assistente AI per la gestione inventario!\n\n"
        "📋 **Cosa posso fare:**\n"
        "• Rispondere alle tue domande\n"
        "• Aiutarti con la gestione inventario\n"
        "• Fornire report e statistiche\n\n"
        "💬 **Come usarmi:**\n"
        "Scrivi semplicemente la tua domanda o usa /help per vedere i comandi.\n\n"
        "🚀 **Pronto ad aiutarti!**"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def help_cmd(update, context):
    help_text = (
        "🤖 **Gio.ia-bot - Comandi disponibili:**\n\n"
        "📋 **Comandi base:**\n"
        "• `/start` - Avvia il bot e mostra il benvenuto\n"
        "• `/help` - Mostra questo messaggio di aiuto\n\n"
        "💬 **Chat AI:**\n"
        "Scrivi qualsiasi messaggio per chattare con l'AI!\n\n"
        "🔧 **Funzionalità:**\n"
        "• Gestione inventario\n"
        "• Report e statistiche\n"
        "• Assistenza AI specializzata\n\n"
        "❓ **Esempi di domande:**\n"
        "• \"Quanto inventario ho di X?\"\n"
        "• \"Fammi un report delle vendite\"\n"
        "• \"Come gestire il magazzino?\"\n\n"
        "🚀 **Inizia subito scrivendo la tua domanda!**"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def chat_handler(update, context):
    try:
        user = update.effective_user
        user_text = update.message.text
        username = user.username or user.first_name or "Unknown"
        
        logger.info(f"Messaggio da {username} (ID: {user.id}): {user_text[:50]}...")
        
        await update.message.reply_text("💭 Sto pensando...")
        reply = get_ai_response(user_text)
        
        await update.message.reply_text(reply)
        logger.info(f"Risposta inviata a {username}")
        
    except Exception as e:
        logger.error(f"Errore in chat_handler: {e}")
        await update.message.reply_text("⚠️ Errore temporaneo. Riprova tra qualche minuto.")


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



