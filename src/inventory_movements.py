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


def word_to_number(word: str) -> Optional[int]:
    """
    Converte numero in lettere italiano in numero intero.
    Supporta numeri comuni da 1 a 20 e multipli di 10 fino a 100.
    """
    word_lower = word.lower().strip()
    
    # Dizionario numeri in lettere
    numbers_map = {
        # 1-20
        'un': 1, 'uno': 1, 'una': 1,
        'due': 2,
        'tre': 3,
        'quattro': 4,
        'cinque': 5,
        'sei': 6,
        'sette': 7,
        'otto': 8,
        'nove': 9,
        'dieci': 10,
        'undici': 11,
        'dodici': 12,
        'tredici': 13,
        'quattordici': 14,
        'quindici': 15,
        'sedici': 16,
        'diciassette': 17,
        'diciotto': 18,
        'diciannove': 19,
        'venti': 20,
        # Multipli di 10
        'trenta': 30,
        'quaranta': 40,
        'cinquanta': 50,
        'sessanta': 60,
        'settanta': 70,
        'ottanta': 80,
        'novanta': 90,
        'cento': 100
    }
    
    return numbers_map.get(word_lower)


class InventoryMovementManager:
    """Gestore movimenti inventario"""
    
    def __init__(self):
        # Pattern per riconoscere movimenti con numeri (cifre o lettere)
        # Pattern alternativi: (\d+) per numeri, (un|uno|una|due|tre|...) per lettere
        number_pattern = r'(\d+|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta|cento)'
        
        # Pattern per riconoscere movimenti (ordinati dalla più specifica alla più generica)
        self.consumo_patterns = [
            r'ho venduto ' + number_pattern + r' bottiglie? di (.+)',
            r'ho consumato ' + number_pattern + r' bottiglie? di (.+)',
            r'ho bevuto ' + number_pattern + r' bottiglie? di (.+)',
            r'ho venduto ' + number_pattern + r' (.+)',  # Senza "bottiglie di"
            r'ho consumato ' + number_pattern + r' (.+)',  # Senza "bottiglie di"
            r'ho bevuto ' + number_pattern + r' (.+)',    # Senza "bottiglie di"
            r'venduto ' + number_pattern + r' (.+)',
            r'consumato ' + number_pattern + r' (.+)',
            r'bevuto ' + number_pattern + r' (.+)',
            number_pattern + r' bottiglie? di (.+) vendute?',
            number_pattern + r' bottiglie? di (.+) consumate?',
            number_pattern + r' bottiglie? di (.+) bevute?'
        ]
        
        self.rifornimento_patterns = [
            r'ho ricevuto ' + number_pattern + r' bottiglie? di (.+)',
            r'ho comprato ' + number_pattern + r' bottiglie? di (.+)',
            r'ho aggiunto ' + number_pattern + r' bottiglie? di (.+)',
            r'ho ricevuto ' + number_pattern + r' (.+)',  # Senza "bottiglie di"
            r'ho comprato ' + number_pattern + r' (.+)',  # Senza "bottiglie di"
            r'ho aggiunto ' + number_pattern + r' (.+)',  # Senza "bottiglie di"
            r'ricevuto ' + number_pattern + r' (.+)',
            r'comprato ' + number_pattern + r' (.+)',
            r'aggiunto ' + number_pattern + r' (.+)',
            number_pattern + r' bottiglie? di (.+) ricevute?',
            number_pattern + r' bottiglie? di (.+) comprate?',
            number_pattern + r' bottiglie? di (.+) aggiunte?'
        ]
    
    def _parse_multiple_movements(self, message_text: str, movement_type: str) -> List[Tuple[int, str]]:
        """
        Analizza un messaggio per trovare movimenti multipli.
        Esempio: "ho consumato 1 etna e 1 fiano" -> [(1, "etna"), (1, "fiano")]
        
        Returns:
            Lista di tuple (quantity, wine_name)
        """
        movements = []
        number_pattern = r'(\d+|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta|cento)'
        
        # Pattern per riconoscere il prefisso del movimento (es. "ho consumato", "consumato", ecc.)
        if movement_type == 'consumo':
            prefix_patterns = [
                r'ho venduto|ho consumato|ho bevuto|venduto|consumato|bevuto',
                r'ho venduto|ho consumato|ho bevuto'
            ]
        else:
            prefix_patterns = [
                r'ho ricevuto|ho comprato|ho aggiunto|ricevuto|comprato|aggiunto',
                r'ho ricevuto|ho comprato|ho aggiunto'
            ]
        
        # Cerca il prefisso del movimento
        prefix_match = None
        for prefix_pattern in prefix_patterns:
            prefix_match = re.search(prefix_pattern, message_text, re.IGNORECASE)
            if prefix_match:
                break
        
        if not prefix_match:
            return movements
        
        # Estrai la parte dopo il prefisso
        prefix_end = prefix_match.end()
        rest_of_message = message_text[prefix_end:].strip()
        
        # Pattern per riconoscere "X vino" o "X bottiglie di vino"
        # Supporta anche "e" come separatore: "1 etna e 1 fiano"
        wine_pattern = rf'{number_pattern}\s+(?:bottiglie?\s+di\s+)?([^e]+?)(?:\s+e\s+{number_pattern}\s+(?:bottiglie?\s+di\s+)?([^e]+?))*(?:\s+e\s+{number_pattern}\s+(?:bottiglie?\s+di\s+)?([^e]+?))*(?:\s+e\s+{number_pattern}\s+(?:bottiglie?\s+di\s+)?([^e]+?))*'
        
        # Cerca tutti i movimenti usando un approccio più semplice: split per " e " dopo il prefisso
        # Pattern: numero + (bottiglie di)? + nome vino
        parts = re.split(r'\s+e\s+', rest_of_message)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Cerca pattern: numero + (bottiglie di)? + nome vino
            match = re.match(rf'^{number_pattern}\s+(?:bottiglie?\s+di\s+)?(.+)$', part, re.IGNORECASE)
            if match:
                quantity_str = match.group(1).strip()
                wine_name = match.group(2).strip()
                
                # Converti quantità
                if quantity_str.isdigit():
                    quantity = int(quantity_str)
                else:
                    quantity = word_to_number(quantity_str)
                    if quantity is None:
                        continue
                
                movements.append((quantity, wine_name))
        
        return movements
    
    async def process_movement_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Processa un messaggio per riconoscere movimenti inventario"""
        user = update.effective_user
        telegram_id = user.id
        message_text = update.message.text.lower().strip()
        original_message = update.message.text.strip()  # Mantieni originale per context
        
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
        
        # Prima prova a riconoscere movimenti multipli
        multiple_consumi = self._parse_multiple_movements(message_text, 'consumo')
        multiple_rifornimenti = self._parse_multiple_movements(message_text, 'rifornimento')
        
        # Se ci sono movimenti multipli, gestiscili
        if len(multiple_consumi) > 1:
            logger.info(f"[MOVEMENT] Rilevati {len(multiple_consumi)} movimenti consumo multipli: {multiple_consumi}")
            # Salva i movimenti multipli nel context per processarli sequenzialmente
            context.user_data['pending_movements'] = [
                {'type': 'consumo', 'quantity': qty, 'wine_name': wine} 
                for qty, wine in multiple_consumi
            ]
            context.user_data['original_message'] = original_message
            # Processa il primo movimento (gli altri verranno processati dopo la selezione)
            return await self._process_consumo(update, context, telegram_id, multiple_consumi[0][1], multiple_consumi[0][0])
        
        if len(multiple_rifornimenti) > 1:
            logger.info(f"[MOVEMENT] Rilevati {len(multiple_rifornimenti)} movimenti rifornimento multipli: {multiple_rifornimenti}")
            # Salva i movimenti multipli nel context per processarli sequenzialmente
            context.user_data['pending_movements'] = [
                {'type': 'rifornimento', 'quantity': qty, 'wine_name': wine} 
                for qty, wine in multiple_rifornimenti
            ]
            context.user_data['original_message'] = original_message
            # Processa il primo movimento (gli altri verranno processati dopo la selezione)
            return await self._process_rifornimento(update, context, telegram_id, multiple_rifornimenti[0][1], multiple_rifornimenti[0][0])
        
        # Cerca pattern di consumo singolo
        for pattern in self.consumo_patterns:
            match = re.search(pattern, message_text, re.IGNORECASE)
            if match:
                quantity_str = match.group(1).strip()
                wine_name = match.group(2).strip()
                
                # Converti quantità (numero o parola) in intero
                if quantity_str.isdigit():
                    quantity = int(quantity_str)
                else:
                    quantity = word_to_number(quantity_str)
                    if quantity is None:
                        logger.warning(f"Numero in lettere non riconosciuto: '{quantity_str}'")
                        continue
                
                logger.info(f"Matched consumo pattern: '{pattern}' -> quantity={quantity} (from '{quantity_str}'), wine={wine_name}")
                return await self._process_consumo(update, context, telegram_id, wine_name, quantity)
        
        # Cerca pattern di rifornimento singolo
        for pattern in self.rifornimento_patterns:
            match = re.search(pattern, message_text, re.IGNORECASE)
            if match:
                quantity_str = match.group(1).strip()
                wine_name = match.group(2).strip()
                
                # Converti quantità (numero o parola) in intero
                if quantity_str.isdigit():
                    quantity = int(quantity_str)
                else:
                    quantity = word_to_number(quantity_str)
                    if quantity is None:
                        logger.warning(f"Numero in lettere non riconosciuto: '{quantity_str}'")
                        continue
                
                logger.info(f"Matched rifornimento pattern: '{pattern}' -> quantity={quantity} (from '{quantity_str}'), wine={wine_name}")
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
            matching_wines = await async_db_manager.search_wines(telegram_id, wine_name, limit=50)
            
            # Se ci sono più corrispondenze, mostra pulsanti per selezione
            if len(matching_wines) > 1:
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini organizzati su più colonne
                keyboard = []
                buttons_per_row = 2  # 2 pulsanti per riga per migliore leggibilità
                
                for i in range(0, len(matching_wines), buttons_per_row):
                    row = []
                    for j in range(buttons_per_row):
                        if i + j < len(matching_wines):
                            wine = matching_wines[i + j]
                            wine_display = wine.name
                            if wine.producer:
                                wine_display += f" ({wine.producer})"
                            if wine.vintage:
                                wine_display += f" {wine.vintage}"
                            
                            # Limita lunghezza testo pulsante per evitare problemi Telegram
                            if len(wine_display) > 30:
                                wine_display = wine_display[:27] + "..."
                            
                            # Callback data: movimento_consumo:{wine_id}:{quantity}
                            callback_data = f"movimento_consumo:{wine.id}:{quantity}"
                            row.append(InlineKeyboardButton(wine_display, callback_data=callback_data))
                    keyboard.append(row)
                
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
            
            # Processor ora ritorna risultato immediatamente (sincrono)
            if result.get('status') == 'success':
                # Job completato immediatamente (elaborazione sincrona)
                success_message = (
                    f"✅ **Consumo registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name', exact_wine_name)}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📉 **Consumate:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
                return True
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                # ✅ Se è un errore di comprensione, NON mostrare errore qui, ritorna False per passare all'AI
                if self._is_comprehension_error(error_msg):
                    logger.info(
                        f"[MOVEMENT] Errore comprensione in process_movement_message: '{error_msg}' - "
                        f"Ritorno False per passare all'AI"
                    )
                    return False  # ✅ Passa all'AI come fallback
                
                # Errore tecnico, mostra e termina
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
            
            # Notifica admin per errore movimento consumo
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                await enqueue_admin_notification(
                    event_type="error",
                    telegram_id=telegram_id,
                    payload={
                        "error_type": "movement_consumo_exception",
                        "error_message": str(e),
                        "error_code": "MOVEMENT_CONSUMO_EXCEPTION",
                        "component": "telegram-ai-bot",
                        "movement_type": "consumo",
                        "wine_name": wine_name,
                        "quantity": quantity,
                        "last_user_message": update.message.text[:200] if update.message and update.message.text else None,
                        "user_visible_error": f"❌ Errore durante il processamento: {str(e)[:200]}"
                    },
                    correlation_id=get_correlation_id(context)
                )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
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
            matching_wines = await async_db_manager.search_wines(telegram_id, wine_name, limit=50)
            
            # Se ci sono più corrispondenze, mostra pulsanti per selezione
            if len(matching_wines) > 1:
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini organizzati su più colonne
                keyboard = []
                buttons_per_row = 2  # 2 pulsanti per riga per migliore leggibilità
                
                for i in range(0, len(matching_wines), buttons_per_row):
                    row = []
                    for j in range(buttons_per_row):
                        if i + j < len(matching_wines):
                            wine = matching_wines[i + j]
                            wine_display = wine.name
                            if wine.producer:
                                wine_display += f" ({wine.producer})"
                            if wine.vintage:
                                wine_display += f" {wine.vintage}"
                            
                            # Limita lunghezza testo pulsante per evitare problemi Telegram
                            if len(wine_display) > 30:
                                wine_display = wine_display[:27] + "..."
                            
                            # Callback data: movimento_rifornimento:{wine_id}:{quantity}
                            callback_data = f"movimento_rifornimento:{wine.id}:{quantity}"
                            row.append(InlineKeyboardButton(wine_display, callback_data=callback_data))
                    keyboard.append(row)
                
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
            
            # Processor ora ritorna risultato immediatamente (sincrono)
            if result.get('status') == 'success':
                # Job completato immediatamente (elaborazione sincrona)
                success_message = (
                    f"✅ **Rifornimento registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name', exact_wine_name)}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
                return True
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                # ✅ Se è un errore di comprensione, NON mostrare errore qui, ritorna False per passare all'AI
                if self._is_comprehension_error(error_msg):
                    logger.info(
                        f"[MOVEMENT] Errore comprensione in process_movement_message: '{error_msg}' - "
                        f"Ritorno False per passare all'AI"
                    )
                    return False  # ✅ Passa all'AI come fallback
                
                # Errore tecnico, mostra e termina
                await self._handle_movement_error(update, wine_name, error_msg, quantity)
                return True
            
        except Exception as e:
            logger.error(f"Errore processamento rifornimento: {e}", exc_info=True)
            await update.message.reply_text("❌ Errore durante il processamento. Riprova.")
            
            # Notifica admin per errore movimento bot
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                user = update.effective_user
                telegram_id = user.id if user else None
                if telegram_id:
                    await enqueue_admin_notification(
                        event_type="error",
                        telegram_id=telegram_id,
                        payload={
                            "error_type": "movement_processing_error",
                            "error_message": str(e),
                            "error_code": "MOVEMENT_PROCESSING_ERROR",
                            "component": "telegram-ai-bot",
                            "movement_type": "rifornimento",
                            "last_user_message": update.message.text[:200] if update.message and update.message.text else None,
                            "user_visible_error": "❌ Errore durante il processamento. Riprova."
                        },
                        correlation_id=get_correlation_id(context)
                    )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
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
            logger.info(
                f"[MOVEMENT] Inizio polling job {job_id} | "
                f"telegram_id={telegram_id}, wine_name='{wine_name}', movement_type={movement_type}"
            )
            
            # Polling job in background
            result = await processor_client.wait_for_job_completion(
                job_id=job_id,
                max_wait_seconds=300,  # 5 minuti massimo per un movimento
                poll_interval=2  # Poll ogni 2 secondi (movimenti sono veloci)
            )
            
            logger.info(
                f"[MOVEMENT] Polling completato per job {job_id} | "
                f"result_status={result.get('status')}, result_keys={list(result.keys())}"
            )
            
            # Estrai dati dal campo 'result' annidato se presente
            result_status = result.get('status')
            
            if result_status == 'completed':
                # Job completato - estrai dati da result
                result_data = result.get('result', {})
                
                logger.info(
                    f"[MOVEMENT] Job {job_id} completed | "
                    f"result_data_type={type(result_data)}, result_data_keys={list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}"
                )
                
                # Se result è una stringa JSON, parsala
                if isinstance(result_data, str):
                    import json
                    try:
                        result_data = json.loads(result_data)
                        logger.info(f"[MOVEMENT] Parsed JSON result_data per job {job_id}")
                    except Exception as json_err:
                        logger.error(f"[MOVEMENT] Errore parsing JSON result_data per job {job_id}: {json_err}")
                        result_data = {}
                
                if result_data.get('status') == 'success':
                    logger.info(
                        f"[MOVEMENT] Job {job_id} success | "
                        f"wine_name={result_data.get('wine_name')}, "
                        f"quantity_before={result_data.get('quantity_before')}, "
                        f"quantity_after={result_data.get('quantity_after')}"
                    )
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
                f"💡 Controlla il nome o usa `/view` per vedere i vini disponibili.\n\n"
                f"🆕 **Per aggiungere un nuovo vino:** usa `/aggiungi`"
            )
        elif 'insufficient' in error_msg.lower() or 'insufficiente' in error_msg.lower():
            await update.message.reply_text(
                f"⚠️ **Quantità insufficiente**\n\n"
                f"🍷 Richieste: {quantity} bottiglie\n\n"
                f"💡 Verifica la quantità disponibile con `/view`."
            )
        else:
            await update.message.reply_text(
                f"❌ **Errore durante l'aggiornamento**\n\n"
                f"{error_msg[:200]}\n\n"
                f"Riprova più tardi."
            )
    
    def _is_comprehension_error(self, error_msg: str) -> bool:
        """
        Identifica se un errore è un errore di comprensione (AI può risolvere).
        Stessa logica di bot.py per coerenza.
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
            "errore sconosciuto",
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
            "nome vino o quantità non validi",
            "quantità non valida",
            "telegram_id non trovato",
        ]
        
        # Controlla prima errori tecnici (priorità)
        for indicator in technical_indicators:
            if indicator in error_lower:
                return False
        
        # Controlla errori di comprensione
        for indicator in comprehension_indicators:
            if indicator in error_lower:
                return True
        
        return False
    
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
    
    async def _process_next_pending_movement(self, message, context: ContextTypes.DEFAULT_TYPE,
                                            telegram_id: int, business_name: str) -> None:
        """
        Helper per processare il prossimo movimento pendente nella lista.
        Gestisce ambiguità e processamento diretto.
        """
        from .processor_client import processor_client
        
        pending_movements = context.user_data.get('pending_movements', [])
        if not pending_movements:
            # Tutti i movimenti sono stati processati
            logger.info("[MOVEMENT] Tutti i movimenti multipli sono stati processati")
            context.user_data.pop('pending_movements', None)
            context.user_data.pop('original_message', None)
            return
        
        next_movement = pending_movements[0]
        logger.info(
            f"[MOVEMENT] Processando movimento multiplo pendente: {next_movement['type']} "
            f"{next_movement['quantity']} {next_movement['wine_name']}"
        )
        
        # Cerca i vini corrispondenti
        matching_wines = await async_db_manager.search_wines(
            telegram_id, next_movement['wine_name'], limit=50
        )
        
        if len(matching_wines) > 1:
            # Ci sono ambiguità, mostra pulsanti
            msg_text = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{next_movement['wine_name']}'**\n\n"
            msg_text += "Quale tra questi intendi?\n\n"
            
            keyboard = []
            buttons_per_row = 2
            
            for i in range(0, len(matching_wines), buttons_per_row):
                row = []
                for j in range(buttons_per_row):
                    if i + j < len(matching_wines):
                        wine = matching_wines[i + j]
                        wine_display = wine.name
                        if wine.producer:
                            wine_display += f" ({wine.producer})"
                        if wine.vintage:
                            wine_display += f" {wine.vintage}"
                        
                        if len(wine_display) > 30:
                            wine_display = wine_display[:27] + "..."
                        
                        callback_data = f"movimento_{next_movement['type']}:{wine.id}:{next_movement['quantity']}"
                        row.append(InlineKeyboardButton(wine_display, callback_data=callback_data))
                keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(msg_text, parse_mode='Markdown', reply_markup=reply_markup)
        elif len(matching_wines) == 1:
            # Una sola corrispondenza, processa direttamente
            exact_wine_name = matching_wines[0].name
            result = await processor_client.process_movement(
                telegram_id=telegram_id,
                business_name=business_name,
                wine_name=exact_wine_name,
                movement_type=next_movement['type'],
                quantity=next_movement['quantity']
            )
            
            if result.get('status') == 'success':
                if next_movement['type'] == 'consumo':
                    msg = (
                        f"✅ **Consumo registrato**\n\n"
                        f"🍷 **Vino:** {result.get('wine_name')}\n"
                        f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                        f"📉 **Consumate:** {next_movement['quantity']} bottiglie\n\n"
                        f"💾 **Movimento salvato** nel sistema"
                    )
                else:
                    msg = (
                        f"✅ **Rifornimento registrato**\n\n"
                        f"🍷 **Vino:** {result.get('wine_name')}\n"
                        f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                        f"📈 **Aggiunte:** {next_movement['quantity']} bottiglie\n\n"
                        f"💾 **Movimento salvato** nel sistema"
                    )
                await message.reply_text(msg, parse_mode='Markdown')
                
                # Rimuovi questo movimento e continua con il prossimo
                pending_movements.pop(0)
                context.user_data['pending_movements'] = pending_movements
                
                # Processa ricorsivamente il prossimo movimento
                if pending_movements:
                    await self._process_next_pending_movement(message, context, telegram_id, business_name)
                else:
                    # Tutti i movimenti completati
                    context.user_data.pop('pending_movements', None)
                    context.user_data.pop('original_message', None)
            else:
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                await message.reply_text(
                    f"❌ **Errore durante il processamento**\n\n{error_msg[:200]}"
                )
        else:
            # Nessuna corrispondenza
            await message.reply_text(
                f"❌ **Vino non trovato**\n\n"
                f"Non ho trovato '{next_movement['wine_name']}' nel tuo inventario."
            )
            # Rimuovi questo movimento e continua con il prossimo
            pending_movements.pop(0)
            context.user_data['pending_movements'] = pending_movements
            if pending_movements:
                await self._process_next_pending_movement(message, context, telegram_id, business_name)
    
    async def process_movement_from_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                             wine_id: int, movement_type: str, quantity: int) -> bool:
        """
        Processa un movimento quando l'utente seleziona un vino dai pulsanti inline.
        Se ci sono movimenti multipli pendenti, continua con il prossimo dopo questo.
        
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
                
                # Controlla se ci sono movimenti multipli pendenti
                pending_movements = context.user_data.get('pending_movements', [])
                if pending_movements:
                    # Rimuovi il movimento appena processato dalla lista
                    # Il primo movimento nella lista è quello appena processato
                    if len(pending_movements) > 0:
                        pending_movements.pop(0)
                        context.user_data['pending_movements'] = pending_movements
                        
                        # Se ci sono ancora movimenti pendenti, processa il prossimo usando la funzione helper
                        if pending_movements:
                            await self._process_next_pending_movement(
                                query.message, context, telegram_id, user.business_name
                            )
                        else:
                            # Tutti i movimenti sono stati processati
                            logger.info("[MOVEMENT] Tutti i movimenti multipli sono stati processati")
                            context.user_data.pop('pending_movements', None)
                            context.user_data.pop('original_message', None)
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
            logger.error(f"Errore processamento movimento da callback: {e}", exc_info=True)
            if update.callback_query:
                await update.callback_query.answer("❌ Errore durante il processamento.", show_alert=True)
            
            # Notifica admin per errore movimento callback
            try:
                from .admin_notifications import enqueue_admin_notification
                from .structured_logging import get_correlation_id
                
                await enqueue_admin_notification(
                    event_type="error",
                    telegram_id=telegram_id,
                    payload={
                        "error_type": "movement_callback_exception",
                        "error_message": str(e),
                        "error_code": "MOVEMENT_CALLBACK_EXCEPTION",
                        "component": "telegram-ai-bot",
                        "movement_type": movement_type,
                        "wine_id": wine_id,
                        "quantity": quantity,
                        "callback_data": update.callback_query.data if update.callback_query and update.callback_query.data else None,
                        "user_visible_error": "❌ Errore durante il processamento."
                    },
                    correlation_id=get_correlation_id(context)
                )
            except Exception as notif_error:
                logger.warning(f"Errore invio notifica admin: {notif_error}")
            
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
