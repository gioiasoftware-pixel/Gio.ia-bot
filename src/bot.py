import os
import logging
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from .ai import get_ai_response
from .database import db_manager
from .onboarding import onboarding_manager
from .inventory import inventory_manager
from .file_upload import file_upload_manager

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
    telegram_id = user.id
    
    logger.info(f"Comando /start da: {username} (ID: {telegram_id})")
    
    # Verifica se l'onboarding è completato
    if not onboarding_manager.is_onboarding_complete(telegram_id):
        # Avvia onboarding
        await update.message.reply_text(
            f"Ciao {username}! 👋\n\n"
            "🤖 Benvenuto in **Gio.ia-bot**!\n"
            "Il tuo assistente AI per la gestione inventario vini.\n\n"
            "📝 Prima di iniziare, completiamo insieme la configurazione del tuo profilo..."
        )
        onboarding_manager.start_onboarding(update, context)
    else:
        # Onboarding già completato
        user_data = db_manager.get_user_by_telegram_id(telegram_id)
        welcome_text = (
            f"Bentornato {username}! 👋\n\n"
            f"🏢 **{user_data.business_name}** - {user_data.business_type}\n"
            f"📍 {user_data.location}\n\n"
            "🤖 **Gio.ia-bot** è pronto ad aiutarti con:\n"
            "• 📦 Gestione inventario vini\n"
            "• 📊 Report e statistiche\n"
            "• 💡 Consigli personalizzati\n\n"
            "💬 Scrivi la tua domanda o usa /help per i comandi!"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def help_cmd(update, context):
    help_text = (
        "🤖 **Gio.ia-bot - Comandi disponibili:**\n\n"
        "📋 **Comandi base:**\n"
        "• `/start` - Avvia il bot o mostra il profilo\n"
        "• `/help` - Mostra questo messaggio di aiuto\n"
        "• `/inventario` - Visualizza il tuo inventario vini\n"
        "• `/aggiungi` - Aggiungi un nuovo vino\n"
        "• `/upload` - Carica inventario da file/foto\n"
        "• `/scorte` - Mostra vini con scorte basse\n\n"
        "💬 **Chat AI intelligente:**\n"
        "Scrivi qualsiasi domanda per ricevere aiuto personalizzato!\n\n"
        "🔧 **Funzionalità avanzate:**\n"
        "• 📊 Analisi inventario personalizzata\n"
        "• ⚠️ Alert scorte basse\n"
        "• 💡 Consigli gestione magazzino\n"
        "• 📈 Report e statistiche\n\n"
        "❓ **Esempi di domande:**\n"
        "• \"Quali vini devo riordinare?\"\n"
        "• \"Fammi un report del mio inventario\"\n"
        "• \"Come organizzare il magazzino?\"\n"
        "• \"Suggeriscimi vini da aggiungere\"\n\n"
        "🚀 **Inizia subito scrivendo la tua domanda!**"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def chat_handler(update, context):
    try:
        user = update.effective_user
        user_text = update.message.text
        username = user.username or user.first_name or "Unknown"
        telegram_id = user.id
        
        logger.info(f"Messaggio da {username} (ID: {telegram_id}): {user_text[:50]}...")
        
        # Gestisci onboarding se in corso
        if onboarding_manager.handle_onboarding_response(update, context):
            return
        
        # Gestisci aggiunta vino se in corso
        if inventory_manager.handle_wine_data(update, context):
            return
        
        await update.message.reply_text("💭 Sto pensando...")
        
        # Chiama AI con contesto utente
        reply = get_ai_response(user_text, telegram_id)
        
        await update.message.reply_text(reply)
        logger.info(f"Risposta inviata a {username}")
        
    except Exception as e:
        logger.error(f"Errore in chat_handler: {e}")
        await update.message.reply_text("⚠️ Errore temporaneo. Riprova tra qualche minuto.")


# Comandi inventario
async def inventario_cmd(update, context):
    """Mostra l'inventario dell'utente"""
    inventory_manager.show_inventory(update, context)


async def aggiungi_cmd(update, context):
    """Avvia l'aggiunta di un vino"""
    inventory_manager.start_add_wine(update, context)


async def scorte_cmd(update, context):
    """Mostra vini con scorte basse"""
    inventory_manager.show_low_stock(update, context)


async def upload_cmd(update, context):
    """Avvia il processo di upload inventario"""
    file_upload_manager.start_upload_process(update, context)


# Gestione callback query
async def callback_handler(update, context):
    """Gestisce le callback query"""
    query = update.callback_query
    query.answer()
    
    # Gestisci callback onboarding
    if onboarding_manager.handle_callback_query(update, context):
        return
    
    # Gestisci callback inventario
    if inventory_manager.handle_wine_callback(update, context):
        return
    
    # Gestisci callback inventario (pulsanti)
    if query.data == "add_wine":
        inventory_manager.start_add_wine(update, context)
    elif query.data == "low_stock":
        inventory_manager.show_low_stock(update, context)
    elif query.data == "full_report":
        # TODO: Implementare report completo
        await query.edit_message_text("📊 Report completo in arrivo...")
    
    # Gestisci callback upload
    elif query.data == "csv_example":
        file_upload_manager.show_csv_example(update, context)
    elif query.data == "cancel_upload":
        await query.edit_message_text("❌ Upload annullato.")


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
    
    # Comandi base
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    
    # Comandi inventario
    app.add_handler(CommandHandler("inventario", inventario_cmd))
    app.add_handler(CommandHandler("aggiungi", aggiungi_cmd))
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("scorte", scorte_cmd))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Message handler (per chat AI e onboarding)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    # File handlers
    app.add_handler(MessageHandler(filters.Document.ALL, file_upload_manager.handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, file_upload_manager.handle_photo))

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



