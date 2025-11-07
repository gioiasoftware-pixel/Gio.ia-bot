import os
import logging
import asyncio
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from .ai import get_ai_response
# db_manager rimosso - usa async_db_manager
from .new_onboarding import new_onboarding_manager
from .inventory import inventory_manager
from .file_upload import file_upload_manager
from .inventory_movements import inventory_movement_manager
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from .logging_config import setup_colored_logging

# Configurazione logging colorato
setup_colored_logging("telegram-bot")
logger = logging.getLogger(__name__)

# Dict globale per tracciare richieste viewer in attesa
# Mappa: telegram_id -> {'event': Event, 'viewer_url': str, 'correlation_id': str}
_viewer_pending_requests = {}
_viewer_pending_lock = asyncio.Lock()

# Dict globale per tracciare job in corso per utente
# Mappa: telegram_id -> {'job_id': str, 'status': str, 'file_name': str, 'started_at': datetime, 'chat_id': int}
_pending_jobs = {}
_pending_jobs_lock = asyncio.Lock()

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
    """Gestisce il comando /start con gestione errori completa."""
    user = update.effective_user
    username = user.username or user.first_name or "Utente"
    telegram_id = user.id
    
    logger.info(f"Comando /start da: {username} (ID: {telegram_id})")
    
    # Verifica se c'è un job in corso per questo utente
    async with _pending_jobs_lock:
        if telegram_id in _pending_jobs:
            job_info = _pending_jobs[telegram_id]
            await update.message.reply_text(
                "🔄 **Stiamo lavorando sul tuo inventario!**\n\n"
                f"📄 **File**: {job_info.get('file_name', 'Sconosciuto')}\n"
                f"⏱️ **Elaborazione in corso...**\n\n"
                f"Ti manderò un messaggio appena pronto! ✅\n\n"
                f"📋 Job ID: `{job_info.get('job_id', 'N/A')}`",
                parse_mode='Markdown'
            )
            return
    
    try:
        # Verifica disponibilità database
        if not DATABASE_AVAILABLE:
            await update.message.reply_text(
                "⚠️ **Database non disponibile**\n\n"
                "Il sistema è temporaneamente in manutenzione.\n"
                "Riprova tra qualche minuto."
            )
            return
        
        # Verifica se l'onboarding è completato - ASYNC (con error handling)
        try:
            is_complete = await new_onboarding_manager.is_onboarding_complete(telegram_id)
        except Exception as onboarding_check_error:
            logger.error(
                f"Errore verifica onboarding per {telegram_id}: {onboarding_check_error}",
                exc_info=True
            )
            # Assumiamo che l'onboarding non sia completato e procediamo
            is_complete = False
        
        if not is_complete:
            # Avvia nuovo onboarding (con error handling)
            try:
                await new_onboarding_manager.start_new_onboarding(update, context)
            except Exception as onboarding_error:
                logger.error(
                    f"Errore avvio onboarding per {telegram_id}: {onboarding_error}",
                    exc_info=True
                )
                await update.message.reply_text(
                    "⚠️ **Errore durante l'onboarding**\n\n"
                    "Si è verificato un errore. Riprova tra qualche istante.\n"
                    "Se il problema persiste, contatta il supporto."
                )
        else:
            # Onboarding già completato - ASYNC (con error handling)
            try:
                from .database_async import async_db_manager
                user_data = await async_db_manager.get_user_by_telegram_id(telegram_id)
                
                # BUG #3 FIX: Verifica che user_data non sia None
                if user_data is None:
                    logger.warning(f"User {telegram_id} non trovato nel database, avvio onboarding")
                    # Se user non esiste, avvia onboarding
                    try:
                        await new_onboarding_manager.start_new_onboarding(update, context)
                    except Exception as onboarding_error:
                        logger.error(
                            f"Errore avvio onboarding per {telegram_id}: {onboarding_error}",
                            exc_info=True
                        )
                        await update.message.reply_text(
                            "⚠️ **Errore durante l'onboarding**\n\n"
                            "Si è verificato un errore. Riprova tra qualche istante."
                        )
                    return
                
                # BUG #3 FIX: Verifica che business_name esista
                business_name = user_data.business_name if hasattr(user_data, 'business_name') and user_data.business_name else "Il tuo locale"
                
                welcome_text = (
                    f"Bentornato {username}! 👋\n\n"
                    f"🏢 **{business_name}**\n\n"
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
                
            except Exception as db_error:
                logger.error(
                    f"Errore database durante /start per {telegram_id}: {db_error}",
                    exc_info=True
                )
                await update.message.reply_text(
                    "⚠️ **Errore di connessione**\n\n"
                    "Si è verificato un errore di connessione al database.\n"
                    "Riprova tra qualche minuto."
                )
                
    except Exception as e:
        # BUG #2 FIX: Cattura tutte le eccezioni non previste
        logger.error(
            f"Errore critico in start_cmd per {telegram_id}: {e}",
            exc_info=True
        )
        try:
            await update.message.reply_text(
                "⚠️ **Errore**\n\n"
                "Si è verificato un errore imprevisto.\n"
                "Riprova tra qualche istante o contatta il supporto."
            )
        except Exception as reply_error:
            logger.error(f"Errore anche nell'invio messaggio errore: {reply_error}")


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


async def view_cmd(update, context):
    """Comando per generare link viewer con token JWT"""
    from .structured_logging import log_with_context, set_request_context, get_correlation_id
    import uuid
    
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Utente"
    
    # Setup correlation_id per logging strutturato
    correlation_id = str(uuid.uuid4())
    set_request_context(telegram_id, correlation_id)
    
    log_with_context(
        "info",
        f"[VIEW] Comando /view ricevuto da {username} (ID: {telegram_id})",
        telegram_id=telegram_id,
        correlation_id=correlation_id
    )
    
    try:
        from .database_async import async_db_manager
        
        log_with_context(
            "info",
            f"[VIEW] Verifica utente e inventario per telegram_id={telegram_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Verifica che utente esista e abbia onboarding completato
        user_db = await async_db_manager.get_user_by_telegram_id(telegram_id)
        
        if not user_db:
            log_with_context(
                "warning",
                f"[VIEW] Utente non trovato per telegram_id={telegram_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            await update.message.reply_text(
                "⚠️ **Utente non trovato**\n\n"
                "Completa prima l'onboarding con `/start`."
            )
            return
        
        log_with_context(
            "info",
            f"[VIEW] Utente trovato: business_name={user_db.business_name}, "
            f"onboarding_completed={user_db.onboarding_completed}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        if not user_db.business_name or user_db.business_name == "Upload Manuale":
            log_with_context(
                "warning",
                f"[VIEW] Business name non configurato per telegram_id={telegram_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            await update.message.reply_text(
                "⚠️ **Nome locale non configurato**\n\n"
                "Completa prima l'onboarding con `/start`."
            )
            return
        
        # Verifica che abbia inventario
        log_with_context(
            "info",
            f"[VIEW] Recupero inventario per telegram_id={telegram_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        user_wines = await async_db_manager.get_user_wines(telegram_id)
        
        log_with_context(
            "info",
            f"[VIEW] Recuperati {len(user_wines) if user_wines else 0} vini da tabella dinamica per "
            f"{telegram_id}/{user_db.business_name}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        if not user_wines or len(user_wines) == 0:
            log_with_context(
                "warning",
                f"[VIEW] Inventario vuoto per telegram_id={telegram_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            await update.message.reply_text(
                "⚠️ **Inventario vuoto**\n\n"
                "Carica prima il tuo inventario con `/upload`."
            )
            return
        
        # Avvia job viewer per generare HTML e link
        log_with_context(
            "info",
            f"[VIEW] Avvio job viewer (genera HTML), "
            f"telegram_id={telegram_id}, business_name={user_db.business_name}, "
            f"correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        import asyncio
        import aiohttp
        
        # URL servizi (usa config se disponibile, altrimenti default)
        from .config import VIEWER_URL as CONFIG_VIEWER_URL
        VIEWER_URL = CONFIG_VIEWER_URL
        
        # Assicura che VIEWER_URL abbia il protocollo
        if VIEWER_URL and not VIEWER_URL.startswith(("http://", "https://")):
            VIEWER_URL = f"https://{VIEWER_URL}"
        
        log_with_context(
            "info",
            f"[VIEW] Configurazione URL viewer: VIEWER_URL={VIEWER_URL}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Job Viewer - genera HTML e invia link al bot
        async def job_viewer():
            try:
                payload = {
                    "telegram_id": telegram_id,
                    "business_name": user_db.business_name,
                    "correlation_id": correlation_id
                }
                
                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{VIEWER_URL}/api/generate",
                        json=payload
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            log_with_context(
                                "info",
                                f"[VIEW_JOB] Viewer generato con successo: view_id={result.get('view_id')}, "
                                f"telegram_id={telegram_id}, correlation_id={correlation_id}",
                                telegram_id=telegram_id,
                                correlation_id=correlation_id
                            )
                        else:
                            error_text = await response.text()
                            log_with_context(
                                "error",
                                f"[VIEW_JOB] Errore generazione viewer: HTTP {response.status}, "
                                f"telegram_id={telegram_id}, error={error_text[:200]}, "
                                f"correlation_id={correlation_id}",
                                telegram_id=telegram_id,
                                correlation_id=correlation_id
                            )
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                log_with_context(
                    "error",
                    f"[VIEW_JOB] Errore job viewer: {e}, telegram_id={telegram_id}, "
                    f"correlation_id={correlation_id}, VIEWER_URL={VIEWER_URL}, "
                    f"error_details={error_details[:500]}",
                    telegram_id=telegram_id,
                    correlation_id=correlation_id,
                    exc_info=True
                )
        
        # Crea Event per attendere il link dal viewer
        viewer_event = asyncio.Event()
        _viewer_pending_requests[telegram_id] = {
            'event': viewer_event,
            'viewer_url': None,
            'correlation_id': correlation_id
        }
        
        log_with_context(
            "info",
            f"[VIEW] Creato Event per attendere link viewer, telegram_id={telegram_id}, correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Messaggio all'utente: link in preparazione
        loading_message = await update.message.reply_text(
            f"⏳ **Generazione link in corso...**\n\n"
            f"📋 Sto preparando il tuo inventario per la visualizzazione.\n\n"
            f"⏱️ Attendo il link...",
            parse_mode='Markdown'
        )
        
        # Avvia job viewer
        asyncio.create_task(job_viewer())
        
        log_with_context(
            "info",
            f"[VIEW] Job viewer avviato, telegram_id={telegram_id}, correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Attendi il link dal viewer (timeout 60 secondi)
        try:
            await asyncio.wait_for(viewer_event.wait(), timeout=60.0)
            
            # Recupera il link dal dict
            async with _viewer_pending_lock:
                pending_data = _viewer_pending_requests.get(telegram_id)
                viewer_url = pending_data.get('viewer_url') if pending_data else None
                # Rimuovi dalla cache
                _viewer_pending_requests.pop(telegram_id, None)
            
            if viewer_url:
                # Modifica il messaggio con il link
        final_message = (
            "<b>🌐 Link Visualizzazione Inventario</b>\n\n"
            "📋 Clicca sul link qui sotto per visualizzare il tuo inventario completo:\n\n"
            f'<a href="{viewer_url}">🔗 Apri Viewer</a>\n\n'
            "⏰ <b>Validità:</b> 1 ora\n"
            "💡 Se il link scade, usa /view per generarne uno nuovo.\n\n"
            f"📊 <b>Vini nel tuo inventario:</b> {len(user_wines)}"
        )
        
        await loading_message.edit_text(final_message, parse_mode=ParseMode.HTML)
                
                log_with_context(
                    "info",
                    f"[VIEW] Link inviato all'utente con successo, telegram_id={telegram_id}, "
                    f"correlation_id={correlation_id}",
                    telegram_id=telegram_id,
                    correlation_id=correlation_id
                )
            else:
                # Timeout o errore
                await loading_message.edit_text(
                    "❌ **Timeout generazione link**\n\n"
                    "Il link non è stato generato entro il tempo previsto.\n"
                    "Riprova con `/view`.",
                    parse_mode='Markdown'
                )
                
                log_with_context(
                    "warning",
                    f"[VIEW] Timeout attesa link (nessun URL), telegram_id={telegram_id}, "
                    f"correlation_id={correlation_id}",
                    telegram_id=telegram_id,
                    correlation_id=correlation_id
                )
                
        except asyncio.TimeoutError:
            # Timeout
            async with _viewer_pending_lock:
                _viewer_pending_requests.pop(telegram_id, None)
            
            await loading_message.edit_text(
                "❌ **Timeout generazione link**\n\n"
                "Il link non è stato generato entro 60 secondi.\n"
                "Riprova con `/view`.",
                parse_mode='Markdown'
            )
            
            log_with_context(
                "warning",
                f"[VIEW] Timeout attesa link (60s), telegram_id={telegram_id}, correlation_id={correlation_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
        
    except Exception as e:
        log_with_context(
            "error",
            f"[VIEW] Errore comando /view: {e}, correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id,
            exc_info=True
        )
        await update.message.reply_text(
            "❌ **Errore generazione link**\n\n"
            "Riprova più tardi."
        )
        
        # Pulisci cache in caso di errore
        async with _viewer_pending_lock:
            _viewer_pending_requests.pop(telegram_id, None)


def _is_comprehension_error(error_msg: str) -> bool:
    """
    Identifica se un errore è un errore di comprensione (AI può risolvere)
    oppure un errore tecnico (AI non può risolvere).
    
    Errori di comprensione (AI può risolvere):
    - Vino non trovato (parsing sbagliato, nome vino malformato)
    - Errori che indicano che l'intent classifier ha capito male
    
    Errori tecnici (NON passare all'AI):
    - Business name non trovato
    - Timeout / HTTP error
    - Errori di connessione
    - Errori di validazione input (campi vuoti)
    """
    if not error_msg:
        return False
    
    error_lower = error_msg.lower()
    
    # Errori di comprensione (AI può risolvere)
    comprehension_indicators = [
        "wine not found",
        "vino non trovato",
        "non ho trovato",
        "non trovato",
        "not found",
        "nessun vino",
        "nessun risultato",
        "no results",
        "errore sconosciuto",  # Quando il parsing è completamente sbagliato
    ]
    
    # Errori tecnici (NON passare all'AI)
    technical_indicators = [
        "business name non trovato",
        "business name non configurato",
        "onboarding",
        "timeout",
        "http error",
        "http client error",
        "connection error",
        "errore connessione",
        "nome vino o quantità non validi",  # Validazione input (campi vuoti)
        "quantità non valida",
        "telegram_id non trovato",
    ]
    
    # Controlla prima errori tecnici (priorità)
    for indicator in technical_indicators:
        if indicator in error_lower:
            return False  # Errore tecnico, NON passare all'AI
    
    # Controlla errori di comprensione
    for indicator in comprehension_indicators:
        if indicator in error_lower:
            return True  # Errore comprensione, passa all'AI
    
    # Default: se non riconosciuto, assume errore tecnico (non passare all'AI)
    return False


async def help_cmd(update, context):
    help_text = (
        "🤖 **Gio.ia-bot - Comandi disponibili:**\n\n"
        "📋 **Comandi base:**\n"
        "• `/start` - Avvia il bot o mostra il profilo\n"
        "• `/help` - Mostra questo messaggio di aiuto\n"
        "• `/view` - Genera link per visualizzare inventario completo\n"
        "• `/aggiungi` - Aggiungi un nuovo vino\n"
        "• `/upload` - Carica inventario da file/foto\n"
        "• `/scorte` - Mostra vini con scorte basse\n"
        "• `/log` - Mostra movimenti inventario\n\n"
        "💬 **Chat AI intelligente:**\n"
        "Scrivi qualsiasi domanda per ricevere aiuto personalizzato!\n\n"
        "❓ **Esempi di domande:**\n"
        "• \"Quali vini ho nell'inventario?\"\n"
        "• \"Che vini ho della Toscana?\"\n"
        "• \"Quanto Barolo ho in cantina?\"\n"
        "• \"Fammi un report del mio inventario\"\n"
        "• \"Quali vini devo riordinare?\"\n\n"
        "💬 **Comunica movimenti:**\n"
        "• \"Ho venduto 2 bottiglie di Chianti\"\n"
        "• \"Ho ricevuto 10 bottiglie di Barolo\"\n"
        "• \"Ho consumato 1 bottiglia di Prosecco\"\n\n"
        "🔧 **Funzionalità disponibili:**\n"
        "• 📊 Analisi inventario personalizzata\n"
        "• ⚠️ Alert scorte basse\n"
        "• 💡 Consigli gestione magazzino\n"
        "• 📈 Report e statistiche\n"
        "• 🔍 Ricerca vini per regione, tipo, paese\n\n"
        "🚀 **Inizia subito scrivendo la tua domanda!**"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def chat_handler(update, context):
    """Gestisce messaggi di chat generici"""
    telegram_id = update.effective_user.id
    
    # Verifica se c'è un job in corso per questo utente
    async with _pending_jobs_lock:
        if telegram_id in _pending_jobs:
            job_info = _pending_jobs[telegram_id]
            await update.message.reply_text(
                "🔄 **Stiamo lavorando sul tuo inventario!**\n\n"
                f"📄 **File**: {job_info.get('file_name', 'Sconosciuto')}\n"
                f"⏱️ **Elaborazione in corso...**\n\n"
                f"Ti manderò un messaggio appena pronto! ✅\n\n"
                f"📋 Job ID: `{job_info.get('job_id', 'N/A')}`\n\n"
                f"💡 Nel frattempo puoi continuare a usare il bot per altre operazioni.",
                parse_mode='Markdown'
            )
            return
    
    # Gestione input per aggiornamento campo vino in sospeso
    pending = context.user_data.get('pending_field_update')
    if pending and update.message and update.message.text:
        try:
            from .processor_client import processor_client
            user = update.effective_user
            telegram_id = user.id
            value_text = update.message.text.strip()
            # Recupera business_name
            from .database_async import async_db_manager
            user_db = await async_db_manager.get_user_by_telegram_id(telegram_id)
            business_name = user_db.business_name if user_db else None
            if not business_name:
                await update.message.reply_text("⚠️ Nome locale non trovato. Completa l'onboarding con /start")
                return
            # Invia aggiornamento al processor
            result = await processor_client.update_wine_field(
                telegram_id=telegram_id,
                business_name=business_name,
                wine_id=pending['wine_id'],
                field=pending['field'],
                value=value_text
            )
            if isinstance(result, dict) and result.get('status') == 'success':
                await update.message.reply_text("✅ Aggiornamento salvato")
            else:
                err = (result or {}).get('error', 'Errore sconosciuto') if isinstance(result, dict) else str(result)
                await update.message.reply_text(f"❌ Errore aggiornamento: {err[:200]}")
        except Exception as e:
            await update.message.reply_text(f"❌ Errore aggiornamento: {str(e)[:200]}")
        finally:
            context.user_data.pop('pending_field_update', None)
        return

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
        
        # Gestisci aggiunta vino se in corso - ASYNC
        if await inventory_manager.handle_wine_data(update, context):
            return
        
        # ✅ NUOVO: Intent Classifier (NO AI) - 5 Retry (PRIMA di process_movement_message per gestire movimenti multipli)
        from .intent_classifier import IntentClassifier
        from .intent_handler import IntentHandler
        
        intent_classifier = IntentClassifier()
        intent = await intent_classifier.classify_with_retry(user_text, telegram_id)
        
        # Se intent trovato (inclusi movimenti multipli), esegui direttamente (NO AI, NO process_movement_message)
        intent_found_but_failed = False  # Flag per tracciare se intent trovato ma esecuzione fallita con errore comprensione
        
        if intent.type != "unknown":
            # Se è un movimento (singolo o multiplo), gestiscilo con Intent Handler
            if intent.type in ["movement_consumption", "movement_replenishment", "multiple_movements"]:
                logger.info(
                    f"[BOT] Movimento riconosciuto: {intent.type} "
                    f"(confidence={intent.confidence:.2f}) - Gestito con Intent Handler"
                )
                
                handler = IntentHandler(telegram_id, context)
                result = await handler.execute_intent(intent)
                
                if result.get("success"):
                    await update.message.reply_text(
                        result.get("formatted_message", "✅ Operazione completata"),
                        parse_mode='Markdown'
                    )
                    return  # ✅ Successo, termina qui
                else:
                    # ✅ FALLBACK AI: Se esecuzione fallisce, controlla se è errore di comprensione
                    error_msg = result.get("error", "Errore sconosciuto")
                    
                    # Controlla se è un errore di comprensione (AI può risolvere)
                    if _is_comprehension_error(error_msg):
                        logger.info(
                            f"[BOT] Esecuzione movimento fallita con errore comprensione: '{error_msg}' - "
                            f"Passando all'AI come fallback"
                        )
                        intent_found_but_failed = True  # ✅ Flag: intent trovato ma fallito con errore comprensione
                        # NON fare return, continua al fallback AI sotto (SALTA process_movement_message)
                    else:
                        # Errore tecnico, mostra e termina
                        await update.message.reply_text(f"❌ {error_msg}")
                        return
            
            # Se è un altro intent (ricerca, lista, etc.), gestiscilo normalmente
            else:
                logger.info(
                    f"[BOT] Intent trovato dopo {intent.retry_count} retry: {intent.type} "
                    f"(confidence={intent.confidence:.2f}) - Gestito SENZA AI"
                )
                
                handler = IntentHandler(telegram_id, context)
                result = await handler.execute_intent(intent)
                
                if result.get("success"):
                    await update.message.reply_text(
                        result.get("formatted_message", "✅ Operazione completata"),
                        parse_mode='Markdown'
                    )
                    return  # ✅ Successo, termina qui
                else:
                    # ✅ FALLBACK AI: Se esecuzione fallisce, controlla se è errore di comprensione
                    error_msg = result.get("error", "Errore sconosciuto")
                    
                    # Controlla se è un errore di comprensione (AI può risolvere)
                    if _is_comprehension_error(error_msg):
                        logger.info(
                            f"[BOT] Esecuzione intent fallita con errore comprensione: '{error_msg}' - "
                            f"Passando all'AI come fallback"
                        )
                        intent_found_but_failed = True  # ✅ Flag: intent trovato ma fallito con errore comprensione
                        # NON fare return, continua al fallback AI sotto (SALTA process_movement_message)
                    else:
                        # Errore tecnico, mostra e termina
                        await update.message.reply_text(f"❌ {error_msg}")
                        return
        
        # ✅ FALLBACK: Se Intent Classifier NON ha riconosciuto (intent.type == "unknown")
        # E NON è un caso di intent trovato ma fallito con errore comprensione
        # Allora prova process_movement_message (per compatibilità)
        if not intent_found_but_failed:
            logger.info(f"[BOT] Intent unknown, provando process_movement_message come fallback...")
            movement_handled = await inventory_movement_manager.process_movement_message(update, context)
            if movement_handled:
                logger.info(f"[BOT] Movement message handled da process_movement_message")
                return
        
        # ✅ FALLBACK AI: Se intent unknown O se esecuzione intent fallita con errore comprensione
        logger.info(f"[BOT] Passando all'AI come fallback (intent unknown o errore comprensione)")
        
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
        
        # Selezione vino quando ci sono più corrispondenze (AI marker)
        if reply and reply.startswith("[[WINE_SELECTION:"):
            try:
                # Estrai termine di ricerca dal marker
                search_term = reply.replace("[[WINE_SELECTION:", "").replace("]]", "").strip()
                
                # Cerca tutti i vini corrispondenti
                matching_wines = await async_db_manager.search_wines(telegram_id, search_term, limit=10)
                
                if len(matching_wines) > 1:
                    message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{search_term}'**\n\n"
                    message += "Quale tra questi intendi?\n\n"
                    
                    # Crea pulsanti inline con i nomi completi dei vini
                    keyboard = []
                    for wine in matching_wines[:5]:  # Max 5 per evitare troppi pulsanti
                        wine_display = wine.name
                        if wine.producer:
                            wine_display += f" ({wine.producer})"
                        if wine.vintage:
                            wine_display += f" {wine.vintage}"
                        
                        # Callback data: wine_info:{wine_id}
                        callback_data = f"wine_info:{wine.id}"
                        keyboard.append([InlineKeyboardButton(wine_display, callback_data=callback_data)])
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                    return
            except Exception as e:
                logger.error(f"Errore gestione selezione vino: {e}")
                # Fallback: continua con risposta normale
        
        # Richiesta periodo movimenti (AI marker)
        if reply and '[[ASK_MOVES_PERIOD]]' in reply:
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗓️ Ultimo giorno", callback_data="movsum:day")],
                    [InlineKeyboardButton("📅 Ultima settimana", callback_data="movsum:week")],
                    [InlineKeyboardButton("🗓️ Ultimo mese", callback_data="movsum:month")],
                ])
                await update.message.reply_text("Per quale periodo vuoi vedere i movimenti?", reply_markup=keyboard)
                return
            except Exception as e:
                logger.error(f"Errore invio bottoni periodo: {e}")
                # fallback: continua

        # Risposta normale AI con eventuali bottoni per compilare/modificare campi
        if reply and ("[[FILL_FIELDS:" in reply or "[[EDIT_FIELDS:" in reply):
            try:
                # Estrai tutti i marker
                fill_marker = None
                edit_marker = None
                
                if "[[FILL_FIELDS:" in reply:
                    fill_start = reply.rfind("[[FILL_FIELDS:")
                    fill_text = reply[fill_start:reply.find("]]", fill_start) + 2] if reply.find("]]", fill_start) >= 0 else None
                    if fill_text:
                        fill_marker = fill_text
                
                if "[[EDIT_FIELDS:" in reply:
                    edit_start = reply.rfind("[[EDIT_FIELDS:")
                    edit_text = reply[edit_start:reply.find("]]", edit_start) + 2] if reply.find("]]", edit_start) >= 0 else None
                    if edit_text:
                        edit_marker = edit_text
                
                # Pulisci reply rimuovendo tutti i marker
                reply_clean = reply
                if fill_marker:
                    reply_clean = reply_clean.replace(fill_marker, "").strip()
                if edit_marker:
                    reply_clean = reply_clean.replace(edit_marker, "").strip()
                reply_clean = reply_clean.rstrip()
                
                # Estrai wine_id e fields da entrambi i marker
                wine_id = None
                fill_fields = []
                edit_fields = []
                
                if fill_marker:
                    marker_inner = fill_marker.strip("[]")
                    parts = marker_inner.split(":", 2)
                    wine_id = int(parts[1]) if len(parts) > 1 else None
                    fill_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                
                if edit_marker:
                    marker_inner = edit_marker.strip("[]")
                    parts = marker_inner.split(":", 2)
                    if wine_id is None:
                        wine_id = int(parts[1]) if len(parts) > 1 else None
                    edit_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                
                # Salva dati nel context per callback successivi
                if wine_id:
                    context.user_data[f'wine_fields_{wine_id}'] = {
                        'fill_fields': fill_fields,
                        'edit_fields': edit_fields,
                        'original_text': reply_clean  # Salva testo originale
                    }
                
                # Mostra solo bottoni principali
                main_buttons = []
                if fill_fields:
                    main_buttons.append([InlineKeyboardButton(
                        "➕ Aggiungi dati",
                        callback_data=f"show_fill:{wine_id}"
                    )])
                if edit_fields:
                    main_buttons.append([InlineKeyboardButton(
                        "📝 Modifica dati",
                        callback_data=f"show_edit:{wine_id}"
                    )])
                
                if main_buttons:
                    keyboard = InlineKeyboardMarkup(main_buttons)
                    await update.message.reply_text(reply_clean, parse_mode='Markdown', reply_markup=keyboard)
                else:
                    await update.message.reply_text(reply_clean, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Errore parsing marker bottoni: {e}")
                await update.message.reply_text(reply, parse_mode='Markdown')
        else:
            await update.message.reply_text(reply, parse_mode='Markdown')
        # Logga risposta assistant
        try:
            await async_db_manager.log_chat_message(telegram_id, 'assistant', reply)
        except Exception:
            pass
        logger.info(f"Risposta inviata a {username}")
        
    except Exception as e:
        logger.error(f"Errore in chat_handler: {e}")
        
        # Notifica admin per errore
        try:
            from .admin_notifications import enqueue_admin_notification
            from .structured_logging import get_correlation_id
            from .database_async import async_db_manager
            
            user = update.effective_user
            telegram_id = user.id if user else None
            
            if telegram_id:
                user_db = await async_db_manager.get_user_by_telegram_id(telegram_id) if telegram_id else None
                business_name = user_db.business_name if user_db else None
                
                await enqueue_admin_notification(
                    event_type="error",
                    telegram_id=telegram_id,
                    payload={
                        "business_name": business_name or "N/A",
                        "error_type": "chat_handler_error",
                        "error_message": str(e),
                        "error_code": "CHAT_ERROR",
                        "component": "telegram-ai-bot",
                        "last_user_message": update.message.text[:200] if update.message and update.message.text else None,
                        "user_visible_error": "⚠️ Errore temporaneo. Riprova tra qualche minuto."
                    },
                    correlation_id=get_correlation_id(context)
                )
        except Exception as notif_error:
            logger.warning(f"Errore invio notifica admin: {notif_error}")
        
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
    
    # Gestisci callback per mostrare bottoni sottomenu
    label_map = {
        "selling_price": "Prezzo vendita",
        "cost_price": "Prezzo acquisto",
        "alcohol_content": "Gradazione",
        "vintage": "Annata",
        "grape_variety": "Vitigno",
        "classification": "Classificazione",
        "description": "Descrizione",
        "notes": "Note",
        "producer": "Produttore",
    }
    
    if query.data and query.data.startswith("show_fill:"):
        try:
            _, wine_id_str = query.data.split(":", 1)
            wine_id = int(wine_id_str)
            fields_data = context.user_data.get(f'wine_fields_{wine_id}', {})
            fill_fields = fields_data.get('fill_fields', [])
            
            if fill_fields:
                buttons = []
                for f in fill_fields:
                    buttons.append([InlineKeyboardButton(
                        f"➕ {label_map.get(f, f)}",
                        callback_data=f"fill:{wine_id}:{f}"
                    )])
                buttons.append([InlineKeyboardButton("◀️ Indietro", callback_data=f"back_main:{wine_id}")])
                keyboard = InlineKeyboardMarkup(buttons)
                await query.edit_message_text("➕ **Aggiungi dati**\n\nSeleziona il campo da compilare:", reply_markup=keyboard)
            return
        except Exception as e:
            logger.error(f"Errore show_fill callback: {e}")
    
    if query.data and query.data.startswith("show_edit:"):
        try:
            _, wine_id_str = query.data.split(":", 1)
            wine_id = int(wine_id_str)
            fields_data = context.user_data.get(f'wine_fields_{wine_id}', {})
            edit_fields = fields_data.get('edit_fields', [])
            
            if edit_fields:
                buttons = []
                for f in edit_fields:
                    buttons.append([InlineKeyboardButton(
                        f"✏️ Modifica {label_map.get(f, f)}",
                        callback_data=f"fill:{wine_id}:{f}"
                    )])
                buttons.append([InlineKeyboardButton("◀️ Indietro", callback_data=f"back_main:{wine_id}")])
                keyboard = InlineKeyboardMarkup(buttons)
                await query.edit_message_text("📝 **Modifica dati**\n\nSeleziona il campo da modificare:", reply_markup=keyboard)
            return
        except Exception as e:
            logger.error(f"Errore show_edit callback: {e}")
    
    if query.data and query.data.startswith("back_main:"):
        try:
            _, wine_id_str = query.data.split(":", 1)
            wine_id = int(wine_id_str)
            fields_data = context.user_data.get(f'wine_fields_{wine_id}', {})
            fill_fields = fields_data.get('fill_fields', [])
            edit_fields = fields_data.get('edit_fields', [])
            original_text = fields_data.get('original_text', query.message.text)
            
            main_buttons = []
            if fill_fields:
                main_buttons.append([InlineKeyboardButton(
                    "➕ Aggiungi dati",
                    callback_data=f"show_fill:{wine_id}"
                )])
            if edit_fields:
                main_buttons.append([InlineKeyboardButton(
                    "📝 Modifica dati",
                    callback_data=f"show_edit:{wine_id}"
                )])
            
            if main_buttons:
                keyboard = InlineKeyboardMarkup(main_buttons)
                await query.edit_message_text(original_text, reply_markup=keyboard, parse_mode='Markdown')
            return
        except Exception as e:
            logger.error(f"Errore back_main callback: {e}")
    
    # Riepilogo movimenti per periodo
    if query.data and query.data.startswith("movsum:"):
        try:
            period = query.data.split(":", 1)[1]
            telegram_id = update.effective_user.id
            from .database_async import get_movement_summary
            from .response_templates import format_movement_period_summary
            summary = await get_movement_summary(telegram_id, period)
            text = format_movement_period_summary(period, summary)
            await query.edit_message_text(text, parse_mode='Markdown')
            return
        except Exception as e:
            logger.error(f"Errore riepilogo movimenti: {e}")
            await query.edit_message_text("⚠️ Errore nel calcolo dei movimenti. Riprova.")
    
    # Gestisci callback di compilazione campi vino
    if query.data and query.data.startswith("fill:"):
        try:
            _, wine_id_str, field = query.data.split(":", 2)
            wine_id = int(wine_id_str)
            context.user_data['pending_field_update'] = {
                'wine_id': wine_id,
                'field': field
            }
            field_label = label_map.get(field, field)
            await query.edit_message_text(f"✏️ Inserisci il valore per: **{field_label}**", parse_mode='Markdown')
            return
        except Exception:
            pass

    # Gestisci callback movimenti (selezione vino da pulsanti)
    if query.data and query.data.startswith("movimento_consumo:"):
        try:
            _, wine_id_str, quantity_str = query.data.split(":")
            wine_id = int(wine_id_str)
            quantity = int(quantity_str)
            if await inventory_movement_manager.process_movement_from_callback(update, context, wine_id, 'consumo', quantity):
                return
        except Exception as e:
            logger.error(f"Errore callback movimento consumo: {e}")
    
    if query.data and query.data.startswith("movimento_rifornimento:"):
        try:
            _, wine_id_str, quantity_str = query.data.split(":")
            wine_id = int(wine_id_str)
            quantity = int(quantity_str)
            if await inventory_movement_manager.process_movement_from_callback(update, context, wine_id, 'rifornimento', quantity):
                return
        except Exception as e:
            logger.error(f"Errore callback movimento rifornimento: {e}")
    
    # Gestisci callback selezione vino per info
    if query.data and query.data.startswith("wine_info:"):
        try:
            from .database_async import async_db_manager
            _, wine_id_str = query.data.split(":")
            wine_id = int(wine_id_str)
            telegram_id = update.effective_user.id
            
            # Recupera il vino dall'ID
            user_wines = await async_db_manager.get_user_wines(telegram_id)
            selected_wine = None
            for wine in user_wines:
                if wine.id == wine_id:
                    selected_wine = wine
                    break
            
            if not selected_wine:
                await query.answer("❌ Vino non trovato.", show_alert=True)
                return
            
            # Mostra info complete del vino
            from .response_templates import format_wine_info
            wine_info_text = format_wine_info(selected_wine)
            
            await query.answer(f"📋 Informazioni su {selected_wine.name}")
            await query.edit_message_text(wine_info_text, parse_mode='Markdown')
            return
        except Exception as e:
            logger.error(f"Errore callback info vino: {e}")
            if update.callback_query:
                await update.callback_query.answer("❌ Errore durante il recupero informazioni.", show_alert=True)
    
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


async def viewer_link_ready_handler(request):
    """
    Endpoint per ricevere link pronto dal viewer.
    """
    from .structured_logging import log_with_context
    
    try:
        # Prova a chiamare request.json() - può essere sync o async
        try:
            if callable(getattr(request, 'json', None)):
                json_method = request.json
                import inspect
                if inspect.iscoroutinefunction(json_method):
                    data = await json_method()
                else:
                    data = json_method()
            else:
                # Fallback per mock request
                data = getattr(request, '_json_data', {})
        except Exception as json_error:
            logger.error(f"[VIEWER_CALLBACK] Errore parsing JSON: {json_error}", exc_info=True)
            return web.Response(
                json={"status": "error", "message": f"Errore parsing JSON: {str(json_error)}"},
                status=400
            )
        
        telegram_id = data.get('telegram_id')
        viewer_url = data.get('viewer_url')
        correlation_id = data.get('correlation_id')
        
        log_with_context(
            "info",
            f"[VIEWER_CALLBACK] Link ricevuto dal viewer: telegram_id={telegram_id}, "
            f"viewer_url={viewer_url[:100]}..., correlation_id={correlation_id}",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        if not telegram_id or not viewer_url:
            log_with_context(
                "warning",
                f"[VIEWER_CALLBACK] Dati mancanti: telegram_id={telegram_id}, viewer_url={bool(viewer_url)}",
                telegram_id=telegram_id if telegram_id else 0,
                correlation_id=correlation_id
            )
            return web.json_response(
                {"status": "error", "message": "telegram_id e viewer_url richiesti"},
                status=400
            )
        
        log_with_context(
            "info",
            f"[VIEWER_CALLBACK] Link pronto per telegram_id={telegram_id}, "
            f"correlation_id={correlation_id}. Sveglio evento...",
            telegram_id=telegram_id,
            correlation_id=correlation_id
        )
        
        # Sveglia l'evento per il comando /view in attesa
        async with _viewer_pending_lock:
            pending_data = _viewer_pending_requests.get(telegram_id)
            if pending_data:
                # Aggiorna il link e sveglia l'evento
                pending_data['viewer_url'] = viewer_url
                event = pending_data.get('event')
                if event:
                    event.set()
                    log_with_context(
                        "info",
                        f"[VIEWER_CALLBACK] Event svegliato per telegram_id={telegram_id}, "
                        f"correlation_id={correlation_id}",
                        telegram_id=telegram_id,
                        correlation_id=correlation_id
                    )
                else:
                    log_with_context(
                        "warning",
                        f"[VIEWER_CALLBACK] Nessun evento trovato per telegram_id={telegram_id}, "
                        f"correlation_id={correlation_id}",
                        telegram_id=telegram_id,
                        correlation_id=correlation_id
                    )
            else:
                log_with_context(
                    "warning",
                    f"[VIEWER_CALLBACK] Nessuna richiesta in attesa per telegram_id={telegram_id}, "
                    f"correlation_id={correlation_id}",
                    telegram_id=telegram_id,
                    correlation_id=correlation_id
                )
        
        return web.json_response(
            {"status": "success", "message": "Link ricevuto e processato"},
            status=200
        )
        
    except Exception as e:
        logger.error(f"[VIEWER_CALLBACK] Errore gestione callback: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500
        )




def _start_health_server(port: int) -> None:
    # Avvia un piccolo server HTTP in un thread separato sulla porta di Railway
    import threading
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed_path = urlparse(self.path)
            if parsed_path.path == "/healthcheck":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(404)
                self.end_headers()
        
        def do_POST(self):
            """Gestisci POST per /api/viewer/link-ready"""
            import asyncio
            from urllib.parse import urlparse
            
            parsed_path = urlparse(self.path)
            logger.info(f"[HEALTH_SERVER] 📥 Richiesta POST ricevuta: path={parsed_path.path}, method={self.command}, client={self.client_address}, headers_count={len(self.headers)}")
            
            # Log headers importanti
            content_type = self.headers.get('Content-Type', 'N/A')
            content_length = self.headers.get('Content-Length', '0')
            logger.info(f"[HEALTH_SERVER] Headers: Content-Type={content_type}, Content-Length={content_length}")
            
            if parsed_path.path == "/api/viewer/link-ready":
                try:
                    logger.info(f"[HEALTH_SERVER] Processing /api/viewer/link-ready")
                    # Leggi body JSON
                    content_length = int(self.headers.get('Content-Length', 0))
                    if content_length == 0:
                        logger.warning(f"[HEALTH_SERVER] Body vuoto per /api/viewer/link-ready")
                        self.send_error(400, "Body vuoto")
                        return
                    
                    body = self.rfile.read(content_length)
                    data = json.loads(body.decode('utf-8'))
                    logger.info(f"[HEALTH_SERVER] Body ricevuto: {json.dumps(data)[:200]}")
                    
                    # Esegui handler asincrono direttamente
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Chiama handler direttamente con i dati (non serve mock request)
                        logger.info(f"[HEALTH_SERVER] Chiamando viewer_link_ready_handler con data: {json.dumps(data)[:200]}")
                        
                        # Crea un oggetto semplice che simula request.json()
                        class SimpleRequest:
                            def __init__(self, json_data):
                                self._json_data = json_data
                            async def json(self):
                                return self._json_data
                        
                        simple_request = SimpleRequest(data)
                        result = loop.run_until_complete(viewer_link_ready_handler(simple_request))
                        logger.info(f"[HEALTH_SERVER] Handler completato, result type: {type(result)}")
                        
                        # Estrai risposta
                        if isinstance(result, web.Response):
                            self.send_response(result.status)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            # web.Response ha text o body
                            if hasattr(result, 'text'):
                                body_text = result.text
                            elif hasattr(result, 'body'):
                                body_text = result.body.decode('utf-8') if isinstance(result.body, bytes) else str(result.body)
                            else:
                                body_text = '{"status":"ok"}'
                            self.wfile.write(body_text.encode('utf-8') if isinstance(body_text, str) else body_text)
                        else:
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
                    finally:
                        loop.close()
                except Exception as e:
                    logger.error(f"Errore gestione POST /api/viewer/link-ready: {e}", exc_info=True)
                    self.send_error(500, f"Internal server error: {e}")
            else:
                self.send_response(404)
                self.end_headers()
        
        def log_message(self, format, *args):
            return  # silenzia il logging di BaseHTTPRequestHandler

    def serve():
        httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"✅ Health server AVVIATO in ascolto su 0.0.0.0:{port} - Gestisce GET /healthcheck e POST /api/viewer/link-ready")
        try:
            httpd.serve_forever()
        except Exception as server_error:
            logger.error(f"❌ Errore health server: {server_error}", exc_info=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()


def main():
    logger.info("=" * 50)
    logger.info("🚀 AVVIO BOT - Inizializzazione...")
    logger.info(f"TELEGRAM_BOT_TOKEN: {'✅ Presente' if TELEGRAM_BOT_TOKEN else '❌ MANCANTE'}")
    logger.info(f"BOT_MODE: {BOT_MODE}")
    logger.info(f"PORT: {PORT}")
    logger.info("=" * 50)
    
    # Configurazione bot senza parametri non supportati
    try:
        logger.info("🔧 Creazione Application builder...")
        builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
        logger.info("✅ Builder creato")
        
        logger.info("🔧 Building Application...")
        app = builder.build()
        logger.info("✅ Application build completato")
    except Exception as e:
        logger.error(f"❌ Errore configurazione bot: {e}", exc_info=True)
        # Fallback con configurazione minima
        logger.info("🔄 Tentativo fallback con configurazione minima...")
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info("✅ Fallback completato")
    
    # Comandi base
    logger.info("📝 Registrazione handlers...")
    app.add_handler(CommandHandler("start", start_cmd))
    logger.info("✅ Handler /start registrato")
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("view", view_cmd))
    app.add_handler(CommandHandler("testai", testai_cmd))
    app.add_handler(CommandHandler("testprocessor", testprocessor_cmd))
    app.add_handler(CommandHandler("deletewebhook", deletewebhook_cmd))
    logger.info("✅ Altri comandi base registrati")
    
    # Comandi inventario
    app.add_handler(CommandHandler("inventario", inventario_cmd))
    app.add_handler(CommandHandler("aggiungi", aggiungi_cmd))
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("scorte", scorte_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    logger.info("✅ Comandi inventario registrati")
    
    # Comando admin (solo per 927230913)
    app.add_handler(CommandHandler("cancellaschema", cancella_schema_cmd))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Message handler (per chat AI e onboarding)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    # File handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document_with_onboarding))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_with_onboarding))
    logger.info("✅ Tutti gli handlers registrati")
    
    # BUG #2 FIX: Error handler per catturare tutte le eccezioni non gestite
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce errori non catturati dagli handler."""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        
        # Prova a inviare messaggio errore se update è valido
        if update and hasattr(update, 'effective_message') and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ **Errore**\n\n"
                    "Si è verificato un errore imprevisto.\n"
                    "Riprova tra qualche istante."
                )
            except Exception as reply_error:
                logger.error(f"Errore invio messaggio errore: {reply_error}")
    
    app.add_error_handler(error_handler)
    logger.info("✅ Error handler registrato")

    # Su Railway usiamo polling + server HTTP per healthcheck sulla PORT
    use_polling_with_health = os.getenv("RAILWAY_ENVIRONMENT") is not None or BOT_MODE != "webhook"
    logger.info(f"🔍 use_polling_with_health: {use_polling_with_health}")
    logger.info(f"🔍 RAILWAY_ENVIRONMENT: {os.getenv('RAILWAY_ENVIRONMENT')}")
    logger.info(f"🔍 BOT_MODE: {BOT_MODE}")
    
    if use_polling_with_health:
        logger.info(f"📡 Starting health server + polling on 0.0.0.0:{PORT}")
        # Avvia server health (thread daemon) e poi polling
        try:
            _start_health_server(PORT)
            logger.info("✅ Health server avviato")
        except Exception as e:
            logger.error(f"❌ Errore avvio health server: {e}", exc_info=True)
        
        # IMPORTANTE: Elimina webhook prima di avviare polling (evita Conflict)
        # Usa chiamata HTTP diretta all'API Telegram (più affidabile)
        logger.info("🔧 Eliminazione webhook esistente (se presente)...")
        try:
            import urllib.request
            import json
            import time
            
            # Chiama direttamente l'API Telegram per eliminare il webhook
            api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
            
            logger.info(f"📡 Chiamata API: {api_url[:50]}...")
            request = urllib.request.Request(api_url, method='POST')
            
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode())
                
                if result.get('ok'):
                    logger.info("✅ Webhook eliminato con successo via API")
                    # Usa asyncio per sleep anche in contesto sync (durante avvio)
                    import time
                    time.sleep(2)  # Attendi 2 secondi per permettere a Telegram di processare
                else:
                    description = result.get('description', 'Unknown error')
                    logger.warning(f"⚠️ Risposta API: {description}")
                    if 'webhook is not set' in description.lower():
                        logger.info("ℹ️ Nessun webhook presente (OK)")
                    else:
                        logger.warning(f"⚠️ Possibile errore eliminazione webhook: {description}")
        except Exception as e:
            logger.error(f"❌ Errore eliminazione webhook via API: {e}", exc_info=True)
            logger.warning("⚠️ Continuo comunque con l'avvio polling...")
        
        # Avvia il polling (bloccante) con gestione conflitti
        # run_polling() dovrebbe eliminare automaticamente il webhook, ma facciamo retry se necessario
        max_retries = 3
        retry_count = 0
        import time
        
        while retry_count < max_retries:
            try:
                if retry_count > 0:
                    logger.info(f"🔄 Tentativo {retry_count + 1}/{max_retries} di avvio polling...")
                    # Tra un tentativo e l'altro, prova di nuovo a eliminare il webhook
                    try:
                        import asyncio
                        async def _delete_webhook_retry():
                            if not app.bot.initialized:
                                await app.bot.initialize()
                            await app.bot.delete_webhook(drop_pending_updates=True)
                            logger.info("✅ Webhook eliminato al retry")
                        
                        try:
                            loop = asyncio.get_event_loop()
                            if not loop.is_running():
                                asyncio.run(_delete_webhook_retry())
                                # Usa asyncio per sleep anche in contesto sync
                                import time
                                time.sleep(3)
                        except RuntimeError:
                            asyncio.run(_delete_webhook_retry())
                            import time
                            time.sleep(3)
                    except Exception as e2:
                        logger.warning(f"⚠️ Errore eliminazione webhook al retry: {e2}")
                    else:
                        import time
                        time.sleep(5)  # Attendi 5 secondi tra i tentativi
                else:
                    logger.info("🔄 Avvio polling...")
                
                # run_polling() elimina automaticamente il webhook se presente
                app.run_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True
                )
                logger.info("✅ Polling avviato con successo")
                break  # Esci dal loop se il polling è partito
            except Exception as e:
                error_msg = str(e)
                if "Conflict" in error_msg or "terminated by other getUpdates" in error_msg:
                    logger.error(f"❌ Conflict: un'altra istanza sta già facendo polling (tentativo {retry_count + 1}/{max_retries})")
                    
                    if retry_count < max_retries - 1:
                        logger.info("🔧 Attendo e riprovo...")
                    else:
                        logger.error(f"❌ Impossibile avviare polling dopo {max_retries} tentativi")
                        logger.error("⚠️ VERIFICA: C'è un'altra istanza del bot in esecuzione su Railway?")
                        logger.error("⚠️ SOLUZIONE: Ferma tutte le istanze del bot e riavvia una sola")
                        raise
                    
                    retry_count += 1
                else:
                    logger.error(f"❌ Errore polling: {e}", exc_info=True)
                    raise  # Rilancia errori non-Conflict
        return

    # Modalità webhook classica (senza health server, non compatibile su PTB 21.5)
    logger.info("📡 Starting bot in webhook mode (senza healthcheck HTTP)")
    logger.info(f"📡 WEBHOOK_URL: {WEBHOOK_URL}")
    try:
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)
        logger.info("✅ Webhook avviato con successo")
    except Exception as e:
        logger.error(f"❌ Errore avvio webhook: {e}", exc_info=True)

if __name__ == "__main__":
    main()



