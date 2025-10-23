import os
import logging
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from .ai import get_ai_response
from .database import db_manager
from .new_onboarding import new_onboarding_manager
from .inventory import inventory_manager
from .file_upload import file_upload_manager
from .inventory_movements import inventory_movement_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verifica se il database è disponibile
DATABASE_AVAILABLE = db_manager.engine is not None
if not DATABASE_AVAILABLE:
    logger.warning("⚠️ Database non disponibile - alcune funzionalità saranno limitate")

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
    
    # Verifica disponibilità database
    if not DATABASE_AVAILABLE:
        await update.message.reply_text(
            "⚠️ **Database non disponibile**\n\n"
            "Il sistema è temporaneamente in manutenzione.\n"
            "Riprova tra qualche minuto."
        )
        return
    
    # Verifica se l'onboarding è completato
    if not new_onboarding_manager.is_onboarding_complete(telegram_id):
        # Avvia nuovo onboarding
        await new_onboarding_manager.start_new_onboarding(update, context)
    else:
        # Onboarding già completato
        user_data = db_manager.get_user_by_telegram_id(telegram_id)
        welcome_text = (
            f"Bentornato {username}! 👋\n\n"
            f"🏢 **{user_data.business_name}**\n\n"
            "🤖 **Gio.ia-bot** è pronto ad aiutarti con:\n"
            "• 📦 Gestione inventario vini\n"
            "• 📊 Report e statistiche\n"
            "• 💡 Consigli personalizzati\n\n"
            "💬 **Comunica i movimenti:**\n"
            "• 'Ho venduto 2 bottiglie di Chianti'\n"
            "• 'Ho ricevuto 10 bottiglie di Barolo'\n\n"
            "📋 Usa /help per tutti i comandi!"
        )
        await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def testai_cmd(update, context):
    """Comando per testare OpenAI API"""
    try:
        from .ai import get_ai_response
        response = get_ai_response("test", update.effective_user.id)
        await update.message.reply_text(f"✅ Test AI: {response[:100]}...")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore test AI: {e}")

async def testprocessor_cmd(update, context):
    """Test connessione processor"""
    import aiohttp
    from .config import PROCESSOR_URL
    
    await update.message.reply_text("🔗 Test connessione processor...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PROCESSOR_URL}/health") as response:
                if response.status == 200:
                    result = await response.json()
                    await update.message.reply_text(
                        f"✅ **Processor connesso!**\n\n"
                        f"URL: {PROCESSOR_URL}\n"
                        f"Status: {result.get('status', 'unknown')}\n"
                        f"Service: {result.get('service', 'unknown')}"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ **Processor non raggiungibile**\n\n"
                        f"URL: {PROCESSOR_URL}\n"
                        f"Status: {response.status}"
                    )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Errore connessione processor**\n\n"
            f"URL: {PROCESSOR_URL}\n"
            f"Errore: {str(e)}"
        )


async def deletewebhook_cmd(update, context):
    """Comando per rimuovere webhook (temporaneo)"""
    try:
        await context.bot.delete_webhook()
        await update.message.reply_text("✅ Webhook rimosso con successo!")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore rimozione webhook: {e}")


async def help_cmd(update, context):
    help_text = (
        "🤖 **Gio.ia-bot - Comandi disponibili:**\n\n"
        "📋 **Comandi base:**\n"
        "• `/start` - Avvia il bot o mostra il profilo\n"
        "• `/help` - Mostra questo messaggio di aiuto\n"
        "• `/inventario` - Visualizza il tuo inventario vini\n"
        "• `/aggiungi` - Aggiungi un nuovo vino\n"
        "• `/upload` - Carica inventario da file/foto\n"
        "• `/scorte` - Mostra vini con scorte basse\n"
        "• `/log` - Mostra movimenti inventario\n\n"
        "💬 **Chat AI intelligente:**\n"
        "Scrivi qualsiasi domanda per ricevere aiuto personalizzato!\n\n"
        "🔧 **Funzionalità avanzate:**\n"
        "• 📊 Analisi inventario personalizzata\n"
        "• ⚠️ Alert scorte basse\n"
        "• 💡 Consigli gestione magazzino\n"
        "• 📈 Report e statistiche\n\n"
        "🛠️ **Comandi tecnici:**\n"
        "• `/testai` - Test connessione AI\n"
        "• `/testprocessor` - Test connessione processor\n\n"
        "❓ **Esempi di domande:**\n"
        "• \"Quali vini devo riordinare?\"\n"
        "• \"Fammi un report del mio inventario\"\n"
        "• \"Come organizzare il magazzino?\"\n"
        "• \"Suggeriscimi vini da aggiungere\"\n\n"
        "💬 **Comunica movimenti:**\n"
        "• \"Ho venduto 2 bottiglie di Chianti\"\n"
        "• \"Ho ricevuto 10 bottiglie di Barolo\"\n"
        "• \"Ho consumato 1 bottiglia di Prosecco\"\n\n"
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
        
        # Verifica disponibilità database
        if not DATABASE_AVAILABLE:
            await update.message.reply_text(
                "⚠️ **Database non disponibile**\n\n"
                "Il sistema è temporaneamente in manutenzione.\n"
                "Riprova tra qualche minuto."
            )
            return
        
        # Gestisci nuovo onboarding se in corso
        if new_onboarding_manager.handle_onboarding_response(update, context):
            return
        
        # Gestisci onboarding guidato dall'AI
        if await new_onboarding_manager.handle_ai_guided_response(update, context):
            return
        
        # Gestisci movimenti inventario
        if inventory_movement_manager.process_movement_message(update, context):
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


async def log_cmd(update, context):
    """Mostra i log dei movimenti inventario"""
    inventory_movement_manager.show_movement_logs(update, context)


async def handle_document_with_onboarding(update, context):
    """Gestisce documenti durante onboarding o normale upload"""
    user = update.effective_user
    telegram_id = user.id
    
    # Verifica se è in onboarding
    if context.user_data.get('onboarding_step') == 'upload_file':
        # Gestisci durante onboarding
        document = update.message.document
        file_data = await context.bot.get_file(document.file_id)
        file_bytes = await file_data.download_as_bytearray()
        
        # Determina tipo file
        file_name = document.file_name.lower()
        if file_name.endswith('.csv'):
            file_type = 'csv'
        elif file_name.endswith(('.xlsx', '.xls')):
            file_type = 'excel'
        else:
            await update.message.reply_text("❌ Formato file non supportato. Usa CSV o Excel.")
            return
        
        # Processa con nuovo onboarding
        new_onboarding_manager.handle_file_upload_during_onboarding(
            update, context, file_type, file_bytes
        )
    elif context.user_data.get('onboarding_step') == 'ai_guided':
        # Gestisci durante onboarding AI
        await new_onboarding_manager.handle_ai_guided_response(update, context)
    else:
        # Gestisci upload normale
        file_upload_manager.handle_document(update, context)


async def handle_photo_with_onboarding(update, context):
    """Gestisce foto durante onboarding o normale upload"""
    user = update.effective_user
    telegram_id = user.id
    
    # Verifica se è in onboarding
    if context.user_data.get('onboarding_step') == 'upload_file':
        # Gestisci durante onboarding
        photo = update.message.photo[-1]  # Prendi la foto più grande
        file_data = await context.bot.get_file(photo.file_id)
        file_bytes = await file_data.download_as_bytearray()
        
        # Processa con nuovo onboarding
        new_onboarding_manager.handle_file_upload_during_onboarding(
            update, context, 'photo', file_bytes
        )
    elif context.user_data.get('onboarding_step') == 'ai_guided':
        # Gestisci durante onboarding AI
        await new_onboarding_manager.handle_ai_guided_response(update, context)
    else:
        # Gestisci upload normale
        file_upload_manager.handle_photo(update, context)


# Gestione callback query
async def callback_handler(update, context):
    """Gestisce le callback query"""
    query = update.callback_query
    query.answer()
    
    # Gestisci callback onboarding (se necessario)
    # if new_onboarding_manager.handle_callback_query(update, context):
    #     return
    
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
    # Configurazione bot senza parametri non supportati
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    
    # Rimuovi eventuali parametri proxy se presenti
    try:
        app = builder.build()
    except Exception as e:
        logger.error(f"Errore configurazione bot: {e}")
        # Fallback con configurazione minima
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Comandi base
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("testai", testai_cmd))
    app.add_handler(CommandHandler("testprocessor", testprocessor_cmd))
    app.add_handler(CommandHandler("deletewebhook", deletewebhook_cmd))
    
    # Comandi inventario
    app.add_handler(CommandHandler("inventario", inventario_cmd))
    app.add_handler(CommandHandler("aggiungi", aggiungi_cmd))
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("scorte", scorte_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Message handler (per chat AI e onboarding)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    # File handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_with_onboarding))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_with_onboarding))

    # Su Railway usiamo polling + server HTTP per healthcheck sulla PORT
    use_polling_with_health = os.getenv("RAILWAY_ENVIRONMENT") is not None or BOT_MODE != "webhook"
    if use_polling_with_health:
        logger.info(f"Starting health server + polling on 0.0.0.0:{PORT}")
        # Avvia server health (thread daemon) e poi polling
        _start_health_server(PORT)
        # Avvia il polling (bloccante) con gestione conflitti
        try:
            app.run_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
        except Exception as e:
            logger.error(f"Errore polling: {e}")
            logger.info("Riprovo polling in 5 secondi...")
            import time
            time.sleep(5)
            app.run_polling(drop_pending_updates=True)
        return

    # Modalità webhook classica (senza health server, non compatibile su PTB 21.5)
    logger.info("Starting bot in webhook mode (senza healthcheck HTTP)")
    app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    main()



