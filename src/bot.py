import os
import logging
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from .ai import get_ai_response
# db_manager rimosso - usa async_db_manager
from .new_onboarding import new_onboarding_manager
from .inventory import inventory_manager
from .file_upload import file_upload_manager
from .inventory_movements import inventory_movement_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Filtra i log httpx/httpcore: mostra solo ERROR
for _lib in ("httpx", "httpcore"):
    logging.getLogger(_lib).addFilter(lambda r: r.levelno >= logging.ERROR)

# Database disponibile verificato dinamicamente in chat_handler
DATABASE_AVAILABLE = True  # Verificato con async_db_manager

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
    
    # Verifica se l'onboarding è completato - ASYNC
    if not await new_onboarding_manager.is_onboarding_complete(telegram_id):
        # Avvia nuovo onboarding
        await new_onboarding_manager.start_new_onboarding(update, context)
    else:
        # Onboarding già completato - ASYNC
        from .database_async import async_db_manager
        user_data = await async_db_manager.get_user_by_telegram_id(telegram_id)
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
    from .processor_client import processor_client
    
    await update.message.reply_text("🔗 Test connessione processor...")
    
    try:
        result = await processor_client.health_check()
        
        if result.get('status') == 'healthy':
            await update.message.reply_text(
                f"✅ **Processor connesso!**\n\n"
                f"URL: {processor_client.base_url}\n"
                f"Status: {result.get('status', 'unknown')}\n"
                f"Service: {result.get('service', 'unknown')}\n"
                f"AI Enabled: {result.get('ai_enabled', 'unknown')}\n"
                f"Database: {result.get('database_status', 'unknown')}"
            )
        else:
            await update.message.reply_text(
                f"❌ **Processor non raggiungibile**\n\n"
                f"URL: {processor_client.base_url}\n"
                f"Status: {result.get('status', 'unknown')}\n"
                f"Error: {result.get('error', 'Unknown error')}"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ **Errore connessione processor**\n\n"
            f"URL: {processor_client.base_url}\n"
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
        "• `/testprocessor` - Test connessione processor\n"
        "• `/cancellaschema <nome>` - [ADMIN] Cancella schema database\n"
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
    # Verifica se c'è una conferma schema delete in sospeso (PRIMA di altre operazioni)
    if await handle_schema_delete_confirmation(update, context):
        return
    
    try:
        from .structured_logging import log_with_context, set_request_context
        from .rate_limiter import check_rate_limit
        from .database_async import async_db_manager
        import uuid
        
        user = update.effective_user
        user_text = update.message.text
        username = user.username or user.first_name or "Unknown"
        telegram_id = user.id
        correlation_id = str(uuid.uuid4())
        update_id = update.update_id
        message_id = update.message.message_id
        
        # ✅ Imposta contesto request
        set_request_context(telegram_id, correlation_id)
        
        log_with_context(
            "info",
            f"Messaggio da {username}: {user_text[:50]}...",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # ✅ RATE LIMITING
        allowed, retry_after = await check_rate_limit(
            telegram_id,
            "message",
            max_requests=20,
            window_seconds=60
        )
        
        if not allowed:
            await update.message.reply_text(
                f"⏳ **Rate limit**\n\n"
                f"Hai inviato troppi messaggi. Riprova tra {retry_after} secondi."
            )
            return
        
        # Verifica disponibilità database (usa async_db_manager per test)
        try:
            test_user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        except Exception as e:
            log_with_context(
                "error",
                f"Database error: {e}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            await update.message.reply_text(
                "⚠️ **Database non disponibile**\n\n"
                "Il sistema è temporaneamente in manutenzione.\n"
                "Riprova tra qualche minuto."
            )
            return
        
        # Gestisci nuovo onboarding se in corso
        if await new_onboarding_manager.handle_onboarding_response(update, context):
            return
        
        # Gestisci onboarding guidato dall'AI
        if await new_onboarding_manager.handle_ai_guided_response(update, context):
            return
        
        # Logga messaggio utente nella chat history
        try:
            await async_db_manager.log_chat_message(telegram_id, 'user', user_text)
        except Exception:
            pass

        # Gestisci movimenti inventario
        logger.info(f"[BOT] Calling process_movement_message for: {user_text[:50]}...")
        movement_handled = await inventory_movement_manager.process_movement_message(update, context)
        if movement_handled:
            logger.info(f"[BOT] Movement message handled, not passing to AI")
            return
        else:
            logger.info(f"[BOT] Movement message NOT handled, passing to AI")
        
        # Gestisci aggiunta vino se in corso - ASYNC
        if await inventory_manager.handle_wine_data(update, context):
            return
        
        await update.message.reply_text("💭 Sto pensando...")
        
        # Chiama AI con contesto utente (async)
        from .ai import get_ai_response
        reply = await get_ai_response(user_text, telegram_id, correlation_id)
        
        # Verifica se l'AI ha rilevato un movimento (marker speciale)
        if reply and reply.startswith("__MOVEMENT__:"):
            # Estrai informazioni movimento dal marker
            parts = reply.split(":")
            if len(parts) >= 4:
                movement_type = parts[1]
                quantity = int(parts[2])
                wine_name = ":".join(parts[3:])  # In caso il nome vino contenga ":"
                
                logger.info(f"[BOT] Processing movement detected by AI: {movement_type} {quantity} {wine_name}")
                
                # Processa movimento in modo asincrono
                from .ai import _process_movement_async
                movement_result = await _process_movement_async(telegram_id, wine_name, movement_type, quantity)
                await update.message.reply_text(movement_result)
                logger.info(f"Movimento processato e risposta inviata a {username}")
                return
        
        # Risposta normale AI
        await update.message.reply_text(reply)
        # Logga risposta assistant
        try:
            await async_db_manager.log_chat_message(telegram_id, 'assistant', reply)
        except Exception:
            pass
        logger.info(f"Risposta inviata a {username}")
        
    except Exception as e:
        logger.error(f"Errore in chat_handler: {e}")
        await update.message.reply_text("⚠️ Errore temporaneo. Riprova tra qualche minuto.")


# Comandi inventario
async def inventario_cmd(update, context):
    """Mostra l'inventario dell'utente"""
    await inventory_manager.show_inventory(update, context)


async def aggiungi_cmd(update, context):
    """Avvia l'aggiunta di un vino"""
    await inventory_manager.start_add_wine(update, context)


async def scorte_cmd(update, context):
    """Mostra vini con scorte basse"""
    await inventory_manager.show_low_stock(update, context)


async def upload_cmd(update, context):
    """Avvia il processo di upload inventario"""
    await file_upload_manager.start_upload_process(update, context)


async def log_cmd(update, context):
    """Mostra i log dei movimenti inventario"""
    await inventory_movement_manager.show_movement_logs(update, context)

async def cancella_schema_cmd(update, context):
    """
    Comando per cancellare schema database.
    SOLO PER telegram_id = 927230913 (admin)
    """
    ADMIN_TELEGRAM_ID = 927230913
    telegram_id = update.effective_user.id
    
    # Verifica autorizzazione
    if telegram_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text(
            "❌ **Non autorizzato**\n\n"
            "Solo l'amministratore può usare questo comando."
        )
        return
    
    # Controlla se è stato fornito il nome locale
    if not context.args:
        await update.message.reply_text(
            "🗑️ **Cancella Schema Database**\n\n"
            "**Uso:** `/cancellaschema <nome_locale>`\n\n"
            "**Esempio:** `/cancellaschema Enoteca Roma`\n\n"
            "⚠️ **ATTENZIONE:** Questa operazione cancella permanentemente:\n"
            "• Tutti i vini nell'inventario\n"
            "• Tutti i backup\n"
            "• Tutti i log movimenti\n\n"
            "L'operazione è irreversibile!"
        )
        return
    
    business_name = " ".join(context.args)
    
    # Chiedi conferma
    context.user_data['pending_schema_delete'] = {
        'business_name': business_name,
        'telegram_id': telegram_id
    }
    
    await update.message.reply_text(
        f"⚠️ **CONFERMA CANCELLAZIONE SCHEMA**\n\n"
        f"📋 **Nome locale:** {business_name}\n"
        f"👤 **Telegram ID:** {telegram_id}\n\n"
        f"⚠️ **Questa operazione è PERMANENTE e IRREVERSIBILE!**\n\n"
        f"Per confermare, rispondi: `CONFERMA CANCELLA`\n"
        f"Per annullare, rispondi: `ANNULLA`",
        parse_mode='Markdown'
    )

async def handle_schema_delete_confirmation(update, context):
    """Gestisce conferma cancellazione schema"""
    ADMIN_TELEGRAM_ID = 927230913
    telegram_id = update.effective_user.id
    
    if telegram_id != ADMIN_TELEGRAM_ID:
        return False
    
    pending = context.user_data.get('pending_schema_delete')
    if not pending:
        return False
    
    user_text = update.message.text.strip().upper()
    
    if user_text == "CONFERMA CANCELLA":
        business_name = pending['business_name']
        
        await update.message.reply_text("🔄 Cancellazione schema in corso...")
        
        from .processor_client import processor_client
        
        result = await processor_client.delete_tables(telegram_id, business_name)
        
        if result.get('success'):
            await update.message.reply_text(
                f"✅ **Tabelle cancellate con successo!**\n\n"
                f"📋 **Locale:** {business_name}\n"
                f"🗑️ **Tutte le tabelle e i dati sono stati rimossi dal database.**",
                parse_mode='Markdown'
            )
        else:
            error_msg = result.get('message', 'Errore sconosciuto')
            await update.message.reply_text(
                f"❌ **Errore cancellazione schema**\n\n"
                f"Dettagli: {error_msg}"
            )
        
        # Pulisci pending
        context.user_data.pop('pending_schema_delete', None)
        return True
    
    elif user_text == "ANNULLA":
        await update.message.reply_text(
            "✅ **Operazione annullata**\n\n"
            "Lo schema non è stato cancellato."
        )
        context.user_data.pop('pending_schema_delete', None)
        return True
    
    return False


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
        await new_onboarding_manager.handle_file_upload_during_onboarding(
            update, context, file_type, file_bytes
        )
    elif context.user_data.get('onboarding_step') == 'ai_guided':
        # Gestisci durante onboarding AI
        await new_onboarding_manager.handle_ai_guided_response(update, context)
    else:
        # Gestisci upload normale - CORREZIONE: Aggiungi await
        await file_upload_manager.handle_document(update, context)


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
        await new_onboarding_manager.handle_file_upload_during_onboarding(
            update, context, 'photo', file_bytes
        )
    elif context.user_data.get('onboarding_step') == 'ai_guided':
        # Gestisci durante onboarding AI
        await new_onboarding_manager.handle_ai_guided_response(update, context)
    else:
        # Gestisci upload normale - CORREZIONE: Aggiungi await
        await file_upload_manager.handle_photo(update, context)


# Gestione callback query
async def callback_handler(update, context):
    """Gestisce le callback query"""
    query = update.callback_query
    query.answer()
    
    # Gestisci callback onboarding (se necessario)
    # if new_onboarding_manager.handle_callback_query(update, context):
    #     return
    
    # Gestisci callback inventario - ASYNC
    if await inventory_manager.handle_wine_callback(update, context):
        return
    
    # Gestisci callback inventario (pulsanti) - ASYNC
    if query.data == "add_wine":
        await inventory_manager.start_add_wine(update, context)
    elif query.data == "low_stock":
        await inventory_manager.show_low_stock(update, context)
    elif query.data == "full_report":
        await query.edit_message_text("📊 Report completo in arrivo...")
    
    # Gestisci callback upload
    elif query.data == "csv_example":
        await file_upload_manager.show_csv_example(update, context)
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
    
    # Comando admin (solo per 927230913)
    app.add_handler(CommandHandler("cancellaschema", cancella_schema_cmd))
    
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



