"""
Gestione movimenti inventario (consumi e rifornimenti)
"""
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database_async import async_db_manager

logger = logging.getLogger(__name__)

class InventoryMovementManager:
    """Gestore movimenti inventario"""
    
    def __init__(self):
        # Pattern per riconoscere movimenti (ordinati dalla più specifica alla più generica)
        self.consumo_patterns = [
            r'ho venduto (\d+) bottiglie? di (.+)',
            r'ho consumato (\d+) bottiglie? di (.+)',
            r'ho bevuto (\d+) bottiglie? di (.+)',
            r'ho venduto (\d+) (.+)',  # Senza "bottiglie di"
            r'ho consumato (\d+) (.+)',  # Senza "bottiglie di" - FIX: aggiunto
            r'ho bevuto (\d+) (.+)',    # Senza "bottiglie di"
            r'venduto (\d+) (.+)',
            r'consumato (\d+) (.+)',
            r'bevuto (\d+) (.+)',
            r'(\d+) bottiglie? di (.+) vendute?',
            r'(\d+) bottiglie? di (.+) consumate?',
            r'(\d+) bottiglie? di (.+) bevute?'
        ]
        
        self.rifornimento_patterns = [
            r'ho ricevuto (\d+) bottiglie? di (.+)',
            r'ho comprato (\d+) bottiglie? di (.+)',
            r'ho aggiunto (\d+) bottiglie? di (.+)',
            r'ho ricevuto (\d+) (.+)',  # Senza "bottiglie di" - FIX: aggiunto
            r'ho comprato (\d+) (.+)',  # Senza "bottiglie di" - FIX: aggiunto
            r'ho aggiunto (\d+) (.+)',  # Senza "bottiglie di" - FIX: aggiunto
            r'ricevuto (\d+) (.+)',
            r'comprato (\d+) (.+)',
            r'aggiunto (\d+) (.+)',
            r'(\d+) bottiglie? di (.+) ricevute?',
            r'(\d+) bottiglie? di (.+) comprate?',
            r'(\d+) bottiglie? di (.+) aggiunte?'
        ]
    
    async def process_movement_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Processa un messaggio per riconoscere movimenti inventario"""
        user = update.effective_user
        telegram_id = user.id
        message_text = update.message.text.lower().strip()
        
        logger.info(f"[MOVEMENT] Checking movement patterns for message: {message_text}")
        
        # Verifica se utente esiste e ha business_name valido + inventario
        user_db = await async_db_manager.get_user_by_telegram_id(telegram_id)  # ASYNC
        if not user_db:
            logger.warning(f"[MOVEMENT] User {telegram_id} not found in database, skipping movement check")
            return False
        
        # Verifica business_name valido (non null e non "Upload Manuale")
        if not user_db.business_name or user_db.business_name == "Upload Manuale":
            logger.info(f"[MOVEMENT] User {telegram_id} non ha business_name valido, skipping movement check")
            return False
        
        # Verifica che l'inventario abbia almeno 1 vino
        user_wines = await async_db_manager.get_user_wines(telegram_id)  # ASYNC
        if not user_wines or len(user_wines) == 0:
            logger.info(f"[MOVEMENT] User {telegram_id} non ha vini nell'inventario, skipping movement check")
            return False
        
        logger.info(f"[MOVEMENT] User {telegram_id} ha business_name '{user_db.business_name}' e {len(user_wines)} vini, checking patterns...")
        
        # Se onboarding non completato ma condizioni sono soddisfatte, completa automaticamente
        if not user_db.onboarding_completed:
            await async_db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                onboarding_completed=True
            )
            logger.info(f"[MOVEMENT] Onboarding completato automaticamente per {telegram_id} (business_name={user_db.business_name}, {len(user_wines)} vini)")
        
        # Cerca pattern di consumo
        for pattern in self.consumo_patterns:
            match = re.search(pattern, message_text)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                logger.info(f"Matched consumo pattern: '{pattern}' -> quantity={quantity}, wine={wine_name}")
                return await self._process_consumo(update, context, telegram_id, wine_name, quantity)
        
        # Cerca pattern di rifornimento
        for pattern in self.rifornimento_patterns:
            match = re.search(pattern, message_text)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                logger.info(f"Matched rifornimento pattern: '{pattern}' -> quantity={quantity}, wine={wine_name}")
                return await self._process_rifornimento(update, context, telegram_id, wine_name, quantity)
        
        logger.debug(f"No movement pattern matched for message: {message_text}")
        return False
    
    async def _process_consumo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                        telegram_id: int, wine_name: str, quantity: int) -> bool:
        """Processa un consumo (quantità negativa) via processor"""
        try:
            from .processor_client import processor_client
            
            # Recupera business_name dal database
            user = await async_db_manager.get_user_by_telegram_id(telegram_id)  # ASYNC
            if not user or not user.business_name:
                await update.message.reply_text(
                    "❌ **Errore**: Nome locale non trovato.\n"
                    "Completa prima l'onboarding con `/start`."
                )
                return True
            
            business_name = user.business_name
            
            # Cerca tutti i vini che corrispondono al termine di ricerca
            matching_wines = await async_db_manager.search_wines(telegram_id, wine_name, limit=10)
            
            # Se ci sono più corrispondenze, mostra pulsanti per selezione
            if len(matching_wines) > 1:
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini
                keyboard = []
                for wine in matching_wines[:5]:  # Max 5 per evitare troppi pulsanti
                    wine_display = wine.name
                    if wine.producer:
                        wine_display += f" ({wine.producer})"
                    if wine.vintage:
                        wine_display += f" {wine.vintage}"
                    
                    # Callback data: movimento_consumo:{wine_id}:{quantity}
                    callback_data = f"movimento_consumo:{wine.id}:{quantity}"
                    keyboard.append([InlineKeyboardButton(wine_display, callback_data=callback_data)])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                return True
            
            # Se c'è una sola corrispondenza o nessuna, procedi normalmente
            if len(matching_wines) == 1:
                # Usa il nome esatto del vino trovato
                exact_wine_name = matching_wines[0].name
            else:
                # Nessuna corrispondenza esatta, prova comunque con il nome originale
                exact_wine_name = wine_name
            
            # Invia movimento al processor (job asincrono)
            logger.info(
                f"[MOVEMENT] Calling processor_client.process_movement | "
                f"telegram_id={telegram_id}, business={business_name}, "
                f"wine_name='{exact_wine_name}', movement_type=consumo, quantity={quantity}"
            )
            
            result = await processor_client.process_movement(
                telegram_id=telegram_id,
                business_name=business_name,
                wine_name=exact_wine_name,
                movement_type='consumo',
                quantity=quantity
            )
            
            logger.info(
                f"[MOVEMENT] Processor response received | "
                f"telegram_id={telegram_id}, wine_name='{exact_wine_name}' | "
                f"status={result.get('status')}, job_id={result.get('job_id')}, "
                f"error={result.get('error')}, error_message={result.get('error_message')}, "
                f"full_result_keys={list(result.keys())}"
            )
            
            # Se il job è in processing, avvia polling in background
            if result.get('status') == 'processing' and result.get('job_id'):
                job_id = result.get('job_id')
                
                # Messaggio iniziale
                await update.message.reply_text(
                    f"⏳ **Elaborazione in corso...**\n\n"
                    f"🍷 Registrando consumo di {quantity} bottiglie di {exact_wine_name}...\n\n"
                    f"Ti invierò un messaggio quando sarà completato."
                )
                
                # Avvia polling in background
                context.application.create_task(
                    self._poll_movement_job_and_notify(
                        telegram_id=telegram_id,
                        job_id=job_id,
                        chat_id=update.effective_chat.id,
                        wine_name=exact_wine_name,
                        quantity=quantity,
                        movement_type='consumo',
                        bot=context.bot
                    )
                )
            elif result.get('status') == 'success' or result.get('status') == 'completed':
                # Job completato immediatamente (non dovrebbe succedere, ma gestiamo)
                success_message = (
                    f"✅ **Consumo registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name', exact_wine_name)}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📉 **Consumate:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                await self._handle_movement_error(update, wine_name, error_msg, quantity)
            
            return True
            
        except Exception as e:
            logger.error(
                f"[MOVEMENT] Exception in _process_consumo | "
                f"telegram_id={telegram_id}, wine_name='{wine_name}', quantity={quantity} | "
                f"error={str(e)}",
                exc_info=True
            )
            await update.message.reply_text(
                f"❌ **Errore durante il processamento**\n\n"
                f"Errore: {str(e)[:200]}\n\n"
                f"Riprova più tardi."
            )
            return True
    
    async def _process_rifornimento(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                             telegram_id: int, wine_name: str, quantity: int) -> bool:
        """Processa un rifornimento (quantità positiva) via processor"""
        try:
            from .processor_client import processor_client
            
            # Recupera business_name dal database
            user = await async_db_manager.get_user_by_telegram_id(telegram_id)  # ASYNC
            if not user or not user.business_name:
                await update.message.reply_text(
                    "❌ **Errore**: Nome locale non trovato.\n"
                    "Completa prima l'onboarding con `/start`."
                )
                return True
            
            business_name = user.business_name
            
            # Cerca tutti i vini che corrispondono al termine di ricerca
            matching_wines = await async_db_manager.search_wines(telegram_id, wine_name, limit=10)
            
            # Se ci sono più corrispondenze, mostra pulsanti per selezione
            if len(matching_wines) > 1:
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini
                keyboard = []
                for wine in matching_wines[:5]:  # Max 5 per evitare troppi pulsanti
                    wine_display = wine.name
                    if wine.producer:
                        wine_display += f" ({wine.producer})"
                    if wine.vintage:
                        wine_display += f" {wine.vintage}"
                    
                    # Callback data: movimento_rifornimento:{wine_id}:{quantity}
                    callback_data = f"movimento_rifornimento:{wine.id}:{quantity}"
                    keyboard.append([InlineKeyboardButton(wine_display, callback_data=callback_data)])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
                return True
            
            # Se c'è una sola corrispondenza o nessuna, procedi normalmente
            if len(matching_wines) == 1:
                # Usa il nome esatto del vino trovato
                exact_wine_name = matching_wines[0].name
            else:
                # Nessuna corrispondenza esatta, prova comunque con il nome originale
                exact_wine_name = wine_name
            
            # Invia movimento al processor (job asincrono)
            result = await processor_client.process_movement(
                telegram_id=telegram_id,
                business_name=business_name,
                wine_name=exact_wine_name,
                movement_type='rifornimento',
                quantity=quantity
            )
            
            logger.info(
                f"[MOVEMENT] Processor response received (rifornimento) | "
                f"telegram_id={telegram_id}, wine_name='{exact_wine_name}' | "
                f"status={result.get('status')}, job_id={result.get('job_id')}"
            )
            
            # Se il job è in processing, avvia polling in background
            if result.get('status') == 'processing' and result.get('job_id'):
                job_id = result.get('job_id')
                
                # Messaggio iniziale
                await update.message.reply_text(
                    f"⏳ **Elaborazione in corso...**\n\n"
                    f"🍷 Registrando rifornimento di {quantity} bottiglie di {exact_wine_name}...\n\n"
                    f"Ti invierò un messaggio quando sarà completato."
                )
                
                # Avvia polling in background
                context.application.create_task(
                    self._poll_movement_job_and_notify(
                        telegram_id=telegram_id,
                        job_id=job_id,
                        chat_id=update.effective_chat.id,
                        wine_name=exact_wine_name,
                        quantity=quantity,
                        movement_type='rifornimento',
                        bot=context.bot
                    )
                )
            elif result.get('status') == 'success' or result.get('status') == 'completed':
                # Job completato immediatamente
                success_message = (
                    f"✅ **Rifornimento registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name', exact_wine_name)}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                await self._handle_movement_error(update, wine_name, error_msg, quantity)
            
            return True
            
        except Exception as e:
            logger.error(f"Errore processamento rifornimento: {e}")
            await update.message.reply_text("❌ Errore durante il processamento. Riprova.")
            return True
    
    async def _poll_movement_job_and_notify(
        self,
        telegram_id: int,
        job_id: str,
        chat_id: int,
        wine_name: str,
        quantity: int,
        movement_type: str,
        bot
    ):
        """
        Background task per polling job movimento e notifica utente quando completato.
        Non blocca handler principale.
        """
        from .processor_client import processor_client
        
        try:
            # Polling job in background
            result = await processor_client.wait_for_job_completion(
                job_id=job_id,
                max_wait_seconds=300,  # 5 minuti massimo per un movimento
                poll_interval=2  # Poll ogni 2 secondi (movimenti sono veloci)
            )
            
            # Estrai dati dal campo 'result' annidato se presente
            result_status = result.get('status')
            
            if result_status == 'completed':
                # Job completato - estrai dati da result
                result_data = result.get('result', {})
                
                # Se result è una stringa JSON, parsala
                if isinstance(result_data, str):
                    import json
                    try:
                        result_data = json.loads(result_data)
                    except:
                        result_data = {}
                
                if result_data.get('status') == 'success':
                    wine_name_result = result_data.get('wine_name', wine_name)
                    quantity_before = result_data.get('quantity_before', 0)
                    quantity_after = result_data.get('quantity_after', 0)
                    
                    if movement_type == 'consumo':
                        message = (
                            f"✅ **Consumo registrato**\n\n"
                            f"🍷 **Vino:** {wine_name_result}\n"
                            f"📦 **Quantità:** {quantity_before} → {quantity_after} bottiglie\n"
                            f"📉 **Consumate:** {quantity} bottiglie\n\n"
                            f"💾 **Movimento salvato** nel sistema"
                        )
                    else:  # rifornimento
                        message = (
                            f"✅ **Rifornimento registrato**\n\n"
                            f"🍷 **Vino:** {wine_name_result}\n"
                            f"📦 **Quantità:** {quantity_before} → {quantity_after} bottiglie\n"
                            f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                            f"💾 **Movimento salvato** nel sistema"
                        )
                    
                    await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                else:
                    # Job completato ma con errore
                    error_msg = result_data.get('error', result_data.get('error_message', 'Errore sconosciuto'))
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ **Errore durante l'elaborazione**\n\n{error_msg[:200]}"
                    )
            elif result_status == 'failed' or result_status == 'error':
                # Job fallito
                error_msg = result.get('error', 'Errore sconosciuto')
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ **Movimento fallito**\n\n{error_msg[:200]}"
                )
            elif result_status == 'timeout':
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⏱️ **Timeout**\n\nIl movimento sta impiegando più tempo del previsto. Verifica lo stato più tardi."
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ **Stato sconosciuto**\n\nIl movimento è in stato: {result_status}"
                )
                
        except Exception as e:
            logger.error(f"Errore in _poll_movement_job_and_notify per job {job_id}: {e}", exc_info=True)
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ **Errore durante il polling**\n\nSi è verificato un errore. Controlla lo stato del movimento più tardi."
                )
            except:
                pass
    
    async def _handle_movement_error(
        self,
        update: Update,
        wine_name: str,
        error_msg: str,
        quantity: int
    ):
        """Gestisce errori durante i movimenti"""
        # Cerca messaggi di errore specifici nel result_data
        if 'wine_not_found' in error_msg.lower() or 'non trovato' in error_msg.lower():
            await update.message.reply_text(
                f"❌ **Vino non trovato**\n\n"
                f"Non ho trovato '{wine_name}' nel tuo inventario.\n"
                f"💡 Controlla il nome o usa `/inventario` per vedere i vini disponibili.\n\n"
                f"🆕 **Per aggiungere un nuovo vino:** usa `/aggiungi`"
            )
        elif 'insufficient' in error_msg.lower() or 'insufficiente' in error_msg.lower():
            await update.message.reply_text(
                f"⚠️ **Quantità insufficiente**\n\n"
                f"🍷 Richieste: {quantity} bottiglie\n\n"
                f"💡 Verifica la quantità disponibile con `/inventario`."
            )
        else:
            await update.message.reply_text(
                f"❌ **Errore durante l'aggiornamento**\n\n"
                f"{error_msg[:200]}\n\n"
                f"Riprova più tardi."
            )
    
    def _find_matching_wine(self, wines: List, wine_name: str) -> Optional[Any]:
        """Trova un vino che corrisponde al nome dato"""
        wine_name_lower = wine_name.lower()
        
        # Cerca corrispondenza esatta
        for wine in wines:
            if wine.name.lower() == wine_name_lower:
                return wine
        
        # Cerca corrispondenza parziale
        for wine in wines:
            if wine_name_lower in wine.name.lower() or wine.name.lower() in wine_name_lower:
                return wine
        
        # Cerca per produttore
        for wine in wines:
            if wine.producer and wine_name_lower in wine.producer.lower():
                return wine
        
        return None
    
    async def show_movement_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          days: int = 7) -> None:
        """Mostra i log dei movimenti"""
        user = update.effective_user
        telegram_id = user.id
        
        logs = await async_db_manager.get_movement_logs(telegram_id, limit=50)  # ASYNC - usa Consumi e rifornimenti
        
        if not logs:
            await update.message.reply_text(
                "📋 **Nessun movimento registrato**\n\n"
                "Non ci sono ancora movimenti nel tuo inventario.\n"
                "💡 Inizia comunicando i consumi e rifornimenti!"
            )
            return
        
        # Filtra per giorni se specificato
        if days > 0:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            logs = [log for log in logs if log['movement_date'] >= cutoff_date]
        
        if not logs:
            await update.message.reply_text(
                f"📋 **Nessun movimento negli ultimi {days} giorni**\n\n"
                "Non ci sono movimenti recenti nel tuo inventario."
            )
            return
        
        # Raggruppa per tipo
        consumi = [log for log in logs if log['movement_type'] == 'consumo']
        rifornimenti = [log for log in logs if log['movement_type'] == 'rifornimento']
        
        message = f"📊 **Log Movimenti - Ultimi {days} giorni**\n\n"
        
        if consumi:
            message += f"📉 **Consumi ({len(consumi)}):**\n"
            for log in consumi[:10]:  # Max 10
                date_str = log['movement_date'].strftime("%d/%m %H:%M")
                message += f"• {date_str} - {log['wine_name']} (-{abs(log['quantity_change'])})\n"
            message += "\n"
        
        if rifornimenti:
            message += f"📈 **Rifornimenti ({len(rifornimenti)}):**\n"
            for log in rifornimenti[:10]:  # Max 10
                date_str = log['movement_date'].strftime("%d/%m %H:%M")
                message += f"• {date_str} - {log['wine_name']} (+{log['quantity_change']})\n"
            message += "\n"
        
        if len(logs) > 20:
            message += f"... e altri {len(logs) - 20} movimenti"
        
        # Aggiungi pulsanti
        keyboard = [
            [InlineKeyboardButton("📊 Report Completo", callback_data="full_movement_report")],
            [InlineKeyboardButton("📅 Ultimi 3 giorni", callback_data="logs_3d"),
             InlineKeyboardButton("📅 Ultima settimana", callback_data="logs_7d")],
            [InlineKeyboardButton("📅 Ultimo mese", callback_data="logs_30d")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def process_movement_from_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                             wine_id: int, movement_type: str, quantity: int) -> bool:
        """
        Processa un movimento quando l'utente seleziona un vino dai pulsanti inline.
        
        Args:
            update: Update Telegram
            context: Context Telegram
            wine_id: ID del vino selezionato
            movement_type: 'consumo' o 'rifornimento'
            quantity: Quantità del movimento
        """
        try:
            from .processor_client import processor_client
            
            query = update.callback_query
            telegram_id = update.effective_user.id
            
            # Recupera business_name e vino
            user = await async_db_manager.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                await query.answer("❌ Errore: Nome locale non trovato.", show_alert=True)
                return True
            
            # Recupera il vino dall'ID
            user_wines = await async_db_manager.get_user_wines(telegram_id)
            selected_wine = None
            for wine in user_wines:
                if wine.id == wine_id:
                    selected_wine = wine
                    break
            
            if not selected_wine:
                await query.answer("❌ Vino non trovato.", show_alert=True)
                return True
            
            # Conferma selezione
            await query.answer(f"🔄 Elaborazione {movement_type} per {selected_wine.name}...")
            
            # Invia movimento al processor
            result = await processor_client.process_movement(
                telegram_id=telegram_id,
                business_name=user.business_name,
                wine_name=selected_wine.name,  # Usa il nome esatto del vino
                movement_type=movement_type,
                quantity=quantity
            )
            
            if result.get('status') == 'success':
                if movement_type == 'consumo':
                    success_message = (
                        f"✅ **Consumo registrato**\n\n"
                        f"🍷 **Vino:** {result.get('wine_name')}\n"
                        f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                        f"📉 **Consumate:** {quantity} bottiglie\n\n"
                        f"💾 **Movimento salvato** nel sistema"
                    )
                else:
                    success_message = (
                        f"✅ **Rifornimento registrato**\n\n"
                        f"🍷 **Vino:** {result.get('wine_name')}\n"
                        f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                        f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                        f"💾 **Movimento salvato** nel sistema"
                    )
                
                await query.edit_message_text(success_message, parse_mode='Markdown')
            else:
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                if 'insufficient' in error_msg.lower() or 'insufficiente' in error_msg.lower():
                    available_qty = result.get('available_quantity', 'N/A')
                    await query.edit_message_text(
                        f"⚠️ **Quantità insufficiente**\n\n"
                        f"📦 Disponibili: {available_qty} bottiglie\n"
                        f"🍷 Richieste: {quantity} bottiglie",
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text(
                        f"❌ **Errore durante l'aggiornamento**\n\n"
                        f"{error_msg[:200]}",
                        parse_mode='Markdown'
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Errore processamento movimento da callback: {e}")
            if update.callback_query:
                await update.callback_query.answer("❌ Errore durante il processamento.", show_alert=True)
            return True
    
    async def get_daily_summary(self, telegram_id: int, date: datetime = None) -> Dict[str, Any]:
        """Ottieni riassunto giornaliero dei movimenti"""
        if date is None:
            date = datetime.utcnow()
        
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
        
        logs = await async_db_manager.get_movement_logs(telegram_id, limit=1000)  # ASYNC - usa Consumi e rifornimenti
        
        # Filtra per data
        daily_logs = [
            log for log in logs 
            if start_date <= log['movement_date'] < end_date
        ]
        
        consumi = [log for log in daily_logs if log['movement_type'] == 'consumo']
        rifornimenti = [log for log in daily_logs if log['movement_type'] == 'rifornimento']
        
        return {
            'date': date.strftime("%d/%m/%Y"),
            'total_movements': len(daily_logs),
            'consumi_count': len(consumi),
            'rifornimenti_count': len(rifornimenti),
            'total_consumed': sum(abs(log['quantity_change']) for log in consumi),
            'total_received': sum(log['quantity_change'] for log in rifornimenti),
            'logs': daily_logs
        }

# Istanza globale del gestore movimenti
inventory_movement_manager = InventoryMovementManager()
