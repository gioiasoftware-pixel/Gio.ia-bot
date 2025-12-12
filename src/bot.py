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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
        "• `/view` - Link al viewer web dell'inventario\n"
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
                # Mostra scheda info aggiornata
                from .database_async import async_db_manager
                from .response_templates import format_wine_info
                
                user_wines = await async_db_manager.get_user_wines(telegram_id)
                updated_wine = None
                for wine in user_wines:
                    if wine.id == pending['wine_id']:
                        updated_wine = wine
                        break
                
                if updated_wine:
                    wine_info = format_wine_info(updated_wine)
                    
                    # Processa marker FILL_FIELDS e EDIT_FIELDS se presenti
                    fill_marker = None
                    edit_marker = None
                    
                    if "[[FILL_FIELDS:" in wine_info:
                        fill_start = wine_info.rfind("[[FILL_FIELDS:")
                        fill_text = wine_info[fill_start:wine_info.find("]]", fill_start) + 2] if wine_info.find("]]", fill_start) >= 0 else None
                        if fill_text:
                            fill_marker = fill_text
                    
                    if "[[EDIT_FIELDS:" in wine_info:
                        edit_start = wine_info.rfind("[[EDIT_FIELDS:")
                        edit_text = wine_info[edit_start:wine_info.find("]]", edit_start) + 2] if wine_info.find("]]", edit_start) >= 0 else None
                        if edit_text:
                            edit_marker = edit_text
                    
                    # Pulisci wine_info rimuovendo i marker
                    wine_info_clean = wine_info
                    if fill_marker:
                        wine_info_clean = wine_info_clean.replace(fill_marker, "").strip()
                    if edit_marker:
                        wine_info_clean = wine_info_clean.replace(edit_marker, "").strip()
                    wine_info_clean = wine_info_clean.rstrip()
                    
                    # Estrai fields dai marker
                    fill_fields = []
                    edit_fields = []
                    
                    if fill_marker:
                        marker_inner = fill_marker.strip("[]")
                        parts = marker_inner.split(":", 2)
                        fill_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                    
                    if edit_marker:
                        marker_inner = edit_marker.strip("[]")
                        parts = marker_inner.split(":", 2)
                        edit_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                    
                    # Salva dati nel context per callback successivi
                    context.user_data[f'wine_fields_{pending["wine_id"]}'] = {
                        'fill_fields': fill_fields,
                        'edit_fields': edit_fields,
                        'original_text': wine_info_clean
                    }
                    
                    # Mostra bottoni se ci sono campi da compilare/modificare
                    main_buttons = []
                    if fill_fields:
                        main_buttons.append([InlineKeyboardButton(
                            "➕ Aggiungi dati",
                            callback_data=f"show_fill:{pending['wine_id']}"
                        )])
                    if edit_fields:
                        main_buttons.append([InlineKeyboardButton(
                            "📝 Modifica dati",
                            callback_data=f"show_edit:{pending['wine_id']}"
                        )])
                    
                    if main_buttons:
                        keyboard = InlineKeyboardMarkup(main_buttons)
                        await update.message.reply_text(
                            f"✅ **Campo aggiornato con successo!**\n\n{wine_info_clean}",
                            parse_mode='Markdown',
                            reply_markup=keyboard
                        )
                    else:
                        await update.message.reply_text(
                            f"✅ **Campo aggiornato con successo!**\n\n{wine_info_clean}",
                            parse_mode='Markdown'
                        )
                else:
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
        
        # Gestione WINE_SELECTION_BUTTONS marker - mostra bottoni per selezione vino
        if reply and '[[WINE_SELECTION_BUTTONS:' in reply:
            try:
                marker_start = reply.find('[[WINE_SELECTION_BUTTONS:')
                marker_end = reply.find(']]', marker_start)
                if marker_start >= 0 and marker_end >= 0:
                    wine_ids_str = reply[marker_start + 27:marker_end]  # 27 = len('[[WINE_SELECTION_BUTTONS:')
                    wine_ids = [int(wid) for wid in wine_ids_str.split(':') if wid.isdigit()]
                    
                    logger.info(f"[BOT] Processing WINE_SELECTION_BUTTONS marker with {len(wine_ids)} wine IDs")
                    
                    # Verifica se il messaggio originale indica un movimento (consumo/rifornimento)
                    # Se sì, non mostrare la scheda info anche se c'è una sola corrispondenza
                    user_message_lower = user_text.lower() if user_text else ""
                    is_movement_request = any(keyword in user_message_lower for keyword in [
                        'ho venduto', 'ho consumato', 'ho bevuto', 'venduto', 'consumato', 'bevuto',
                        'ho ricevuto', 'ho comprato', 'ho aggiunto', 'ricevuto', 'comprato', 'aggiunto',
                        'rifornimento', 'consumo'
                    ])
                    
                    # Recupera vini dal database
                    from .database_async import async_db_manager
                    user_wines = await async_db_manager.get_user_wines(telegram_id)
                    
                    # Filtra solo i vini richiesti
                    selected_wines = [w for w in user_wines if w.id in wine_ids]
                    
                    if selected_wines:
                        # Se c'è una sola corrispondenza E non è una richiesta di movimento, mostra direttamente la scheda info
                        if len(selected_wines) == 1 and not is_movement_request:
                            from .response_templates import format_wine_info
                            wine = selected_wines[0]
                            wine_info = format_wine_info(wine)
                            
                            # Processa marker FILL_FIELDS e EDIT_FIELDS se presenti
                            fill_marker = None
                            edit_marker = None
                            
                            if "[[FILL_FIELDS:" in wine_info:
                                fill_start = wine_info.rfind("[[FILL_FIELDS:")
                                fill_text = wine_info[fill_start:wine_info.find("]]", fill_start) + 2] if wine_info.find("]]", fill_start) >= 0 else None
                                if fill_text:
                                    fill_marker = fill_text
                            
                            if "[[EDIT_FIELDS:" in wine_info:
                                edit_start = wine_info.rfind("[[EDIT_FIELDS:")
                                edit_text = wine_info[edit_start:wine_info.find("]]", edit_start) + 2] if wine_info.find("]]", edit_start) >= 0 else None
                                if edit_text:
                                    edit_marker = edit_text
                            
                            # Pulisci wine_info rimuovendo i marker
                            wine_info_clean = wine_info
                            if fill_marker:
                                wine_info_clean = wine_info_clean.replace(fill_marker, "").strip()
                            if edit_marker:
                                wine_info_clean = wine_info_clean.replace(edit_marker, "").strip()
                            wine_info_clean = wine_info_clean.rstrip()
                            
                            # Estrai wine_id e fields dai marker
                            wine_id = wine.id
                            fill_fields = []
                            edit_fields = []
                            
                            if fill_marker:
                                marker_inner = fill_marker.strip("[]")
                                parts = marker_inner.split(":", 2)
                                fill_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                            
                            if edit_marker:
                                marker_inner = edit_marker.strip("[]")
                                parts = marker_inner.split(":", 2)
                                edit_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                            
                            # Salva dati nel context per callback successivi
                            if wine_id:
                                context.user_data[f'wine_fields_{wine_id}'] = {
                                    'fill_fields': fill_fields,
                                    'edit_fields': edit_fields,
                                    'original_text': wine_info_clean
                                }
                            
                            # Mostra bottoni se ci sono campi da compilare/modificare
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
                                await update.message.reply_text(wine_info_clean, parse_mode='Markdown', reply_markup=keyboard)
                            else:
                                await update.message.reply_text(wine_info_clean, parse_mode='Markdown')
                            return
                        
                        # Se ci sono più corrispondenze, mostra bottoni per selezione
                        message = f"🔍 **Ho trovato {len(selected_wines)} vini che corrispondono alla tua ricerca**\n\n"
                        message += "Seleziona quale vuoi vedere:\n\n"
                        
                        # Crea bottoni inline organizzati su più colonne
                        keyboard = []
                        buttons_per_row = 2  # 2 pulsanti per riga per migliore leggibilità
                        
                        for i in range(0, len(selected_wines), buttons_per_row):
                            row = []
                            for j in range(buttons_per_row):
                                if i + j < len(selected_wines):
                                    wine = selected_wines[i + j]
                                    wine_display = wine.name
                                    if wine.producer:
                                        wine_display += f" ({wine.producer})"
                                    if wine.vintage:
                                        wine_display += f" {wine.vintage}"
                                    
                                    # Limita lunghezza testo pulsante per evitare problemi Telegram
                                    if len(wine_display) > 30:
                                        wine_display = wine_display[:27] + "..."
                                    
                                    # Callback data: wine_info:{wine_id}
                                    callback_data = f"wine_info:{wine.id}"
                                    row.append(InlineKeyboardButton(wine_display, callback_data=callback_data))
                            keyboard.append(row)
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                        return
            except Exception as e:
                logger.error(f"Errore gestione WINE_SELECTION_BUTTONS marker: {e}", exc_info=True)
        
        # Gestione WINE_SELECTION marker - mostra risultati ricerca vini (legacy)
        if reply and '[[WINE_SELECTION:' in reply:
            try:
                # Estrai termine di ricerca dal marker
                marker_start = reply.find('[[WINE_SELECTION:')
                marker_end = reply.find(']]', marker_start)
                if marker_start >= 0 and marker_end >= 0:
                    search_term = reply[marker_start + 17:marker_end]  # 17 = len("[[WINE_SELECTION:")
                    
                    logger.info(f"[BOT] Processing WINE_SELECTION marker for search term: {search_term}")
                    
                    # Cerca vini nel database
                    from .database_async import async_db_manager
                    from .response_templates import format_inventory_list
                    
                    found_wines = await async_db_manager.search_wines(telegram_id, search_term, limit=50)
                    
                    if found_wines:
                        # Mostra risultati formattati
                        formatted_response = format_inventory_list(found_wines, limit=50)
                        await update.message.reply_text(formatted_response, parse_mode='Markdown')
                        logger.info(f"[BOT] Mostrati {len(found_wines)} vini per ricerca '{search_term}'")
                        return
                    else:
                        # Nessun vino trovato
                        await update.message.reply_text(
                            f"❌ **Nessun vino trovato**\n\n"
                            f"Non ho trovato vini corrispondenti a '{search_term}' nel tuo inventario.\n\n"
                            f"💡 Prova con un termine di ricerca diverso o usa `/view` per vedere tutto l'inventario."
                        )
                        return
            except Exception as e:
                logger.error(f"Errore gestione WINE_SELECTION marker: {e}", exc_info=True)
                # Fallback: continua con risposta normale

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


async def view_cmd(update, context):
    """Genera e invia link al viewer dell'inventario"""
    user = update.effective_user
    telegram_id = user.id
    
    try:
        from .database_async import async_db_manager
        from .viewer_utils import generate_viewer_token, get_viewer_url
        
        # Verifica se l'utente ha completato l'onboarding
        user_data = await async_db_manager.get_user_by_telegram_id(telegram_id)
        
        if not user_data or not user_data.business_name:
            await update.message.reply_text(
                "⚠️ **Onboarding non completato**\n\n"
                "Completa prima l'onboarding con `/start` per accedere al viewer."
            )
            return
        
        # Genera token JWT
        token = generate_viewer_token(telegram_id, user_data.business_name)
        
        if not token:
            await update.message.reply_text(
                "❌ **Errore generazione link**\n\n"
                "Impossibile generare il link al viewer. Riprova tra qualche momento."
            )
            return
        
        # Genera URL completo
        viewer_url = get_viewer_url(token)
        
        await update.message.reply_text(
            f"🔗 **Link al tuo inventario**\n\n"
            f"📋 **Locale:** {user_data.business_name}\n\n"
            f"👉 [Apri inventario nel viewer]({viewer_url})\n\n"
            f"💡 Il link è valido per 1 ora.",
            parse_mode='Markdown',
            disable_web_page_preview=False
        )
        
    except Exception as e:
        logger.error(f"Errore comando /view: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ **Errore**\n\n"
            "Si è verificato un errore. Riprova tra qualche momento."
        )

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
    
    # Gestisci callback movimenti (consumo/rifornimento) PRIMA di answer()
    if query.data and (query.data.startswith("movimento_consumo:") or query.data.startswith("movimento_rifornimento:")):
        try:
            # Estrai dati dal callback
            parts = query.data.split(":")
            movement_type = "consumo" if parts[0] == "movimento_consumo" else "rifornimento"
            wine_id = int(parts[1])
            quantity = int(parts[2])
            
            # Gestisci movimento tramite inventory_movement_manager
            handled = await inventory_movement_manager.process_movement_from_callback(
                update, context, wine_id, movement_type, quantity
            )
            if handled:
                return
        except Exception as e:
            logger.error(f"Errore gestione callback movimento: {e}", exc_info=True)
            await query.answer("❌ Errore durante il processamento.", show_alert=True)
            
            # Notifica admin per errore callback movimento
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                telegram_id = update.effective_user.id if update.effective_user else None
                if telegram_id:
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "error_type": "callback_movement_error",
                            "error_message": str(e),
                            "error_code": "CALLBACK_MOVEMENT_ERROR",
                            "component": "telegram-ai-bot",
                            "callback_data": query.data if query.data else None,
                            "user_visible_error": "❌ Errore durante il processamento."
                        },
                        correlation_id=get_correlation_id(context)
                    )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
            return
    
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
            logger.error(f"Errore show_fill callback: {e}", exc_info=True)
            
            # Notifica admin per errore callback
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                telegram_id = update.effective_user.id if update.effective_user else None
                if telegram_id:
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "error_type": "callback_show_fill_error",
                            "error_message": str(e),
                            "error_code": "CALLBACK_SHOW_FILL_ERROR",
                            "component": "telegram-ai-bot",
                            "callback_data": query.data if query.data else None
                        },
                        correlation_id=get_correlation_id(context)
                    )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
    
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
            logger.error(f"Errore show_edit callback: {e}", exc_info=True)
            
            # Notifica admin per errore callback
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                telegram_id = update.effective_user.id if update.effective_user else None
                if telegram_id:
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "error_type": "callback_show_edit_error",
                            "error_message": str(e),
                            "error_code": "CALLBACK_SHOW_EDIT_ERROR",
                            "component": "telegram-ai-bot",
                            "callback_data": query.data if query.data else None
                        },
                        correlation_id=get_correlation_id(context)
                    )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
    
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
            logger.error(f"Errore back_main callback: {e}", exc_info=True)
            
            # Notifica admin per errore callback
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                telegram_id = update.effective_user.id if update.effective_user else None
                if telegram_id:
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "error_type": "callback_back_main_error",
                            "error_message": str(e),
                            "error_code": "CALLBACK_BACK_MAIN_ERROR",
                            "component": "telegram-ai-bot",
                            "callback_data": query.data if query.data else None
                        },
                        correlation_id=get_correlation_id(context)
                    )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
    
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

    # Gestisci callback info vino (wine_info:{wine_id})
    if query.data and query.data.startswith("wine_info:"):
        try:
            wine_id = int(query.data.split(":")[1])
            telegram_id = update.effective_user.id
            
            from .database_async import async_db_manager
            from .response_templates import format_wine_info
            
            user_wines = await async_db_manager.get_user_wines(telegram_id)
            selected_wine = None
            for wine in user_wines:
                if wine.id == wine_id:
                    selected_wine = wine
                    break
            
            if selected_wine:
                wine_info = format_wine_info(selected_wine)
                
                # Processa marker FILL_FIELDS e EDIT_FIELDS se presenti
                fill_marker = None
                edit_marker = None
                
                if "[[FILL_FIELDS:" in wine_info:
                    fill_start = wine_info.rfind("[[FILL_FIELDS:")
                    fill_text = wine_info[fill_start:wine_info.find("]]", fill_start) + 2] if wine_info.find("]]", fill_start) >= 0 else None
                    if fill_text:
                        fill_marker = fill_text
                
                if "[[EDIT_FIELDS:" in wine_info:
                    edit_start = wine_info.rfind("[[EDIT_FIELDS:")
                    edit_text = wine_info[edit_start:wine_info.find("]]", edit_start) + 2] if wine_info.find("]]", edit_start) >= 0 else None
                    if edit_text:
                        edit_marker = edit_text
                
                # Pulisci wine_info rimuovendo i marker
                wine_info_clean = wine_info
                if fill_marker:
                    wine_info_clean = wine_info_clean.replace(fill_marker, "").strip()
                if edit_marker:
                    wine_info_clean = wine_info_clean.replace(edit_marker, "").strip()
                wine_info_clean = wine_info_clean.rstrip()
                
                # Estrai fields dai marker
                fill_fields = []
                edit_fields = []
                
                if fill_marker:
                    marker_inner = fill_marker.strip("[]")
                    parts = marker_inner.split(":", 2)
                    fill_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                
                if edit_marker:
                    marker_inner = edit_marker.strip("[]")
                    parts = marker_inner.split(":", 2)
                    edit_fields = [f for f in parts[2].split(",") if f][:6] if len(parts) > 2 else []
                
                # Salva dati nel context per callback successivi
                context.user_data[f'wine_fields_{wine_id}'] = {
                    'fill_fields': fill_fields,
                    'edit_fields': edit_fields,
                    'original_text': wine_info_clean
                }
                
                # Mostra bottoni se ci sono campi da compilare/modificare
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
                    await query.edit_message_text(wine_info_clean, parse_mode='Markdown', reply_markup=keyboard)
                else:
                    await query.edit_message_text(wine_info_clean, parse_mode='Markdown')
            else:
                await query.answer("❌ Vino non trovato.", show_alert=True)
            return
        except Exception as e:
            logger.error(f"Errore gestione callback wine_info: {e}", exc_info=True)
            await query.answer("❌ Errore durante il caricamento.", show_alert=True)
            
            # Notifica admin per errore callback
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                await enqueue_admin_notification(
                    event_type="error",
                    telegram_id=telegram_id,
                    payload={
                        "error_type": "callback_wine_info_error",
                        "error_message": str(e),
                        "error_code": "CALLBACK_WINE_INFO_ERROR",
                        "component": "telegram-ai-bot",
                        "callback_data": query.data if query.data else None,
                        "user_visible_error": "❌ Errore durante il caricamento."
                    },
                    correlation_id=get_correlation_id(context)
                )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
            return

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
    app.add_handler(CommandHandler("aggiungi", aggiungi_cmd))
    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("scorte", scorte_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    app.add_handler(CommandHandler("view", view_cmd))
    
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



