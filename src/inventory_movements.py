"""
Gestione movimenti inventario (consumi e rifornimenti)
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database_async import async_db_manager
from .movement_patterns import (
    CONSUMO_PATTERNS, RIFORNIMENTO_PATTERNS, parse_multiple_movements,
    parse_single_movement, word_to_number
)
from .movement_utils import (
    fuzzy_match_wine_name, is_comprehension_error,
    format_movement_error_message, format_movement_success_message
)

logger = logging.getLogger(__name__)


def _identify_differentiating_field(wines: List[Any]) -> Tuple[Optional[str], str]:
    """
    Identifica quale campo differenzia i vini quando hanno lo stesso nome.
    
    Args:
        wines: Lista di oggetti Wine
        
    Returns:
        Tuple (nome_campo, etichetta_utente): Il campo che differenzia i vini e la sua etichetta
    """
    if len(wines) < 2:
        return None, ""
    
    # Verifica se tutti hanno lo stesso nome
    first_name = wines[0].name.lower().strip() if wines[0].name else ""
    all_same_name = all(
        (w.name.lower().strip() if w.name else "") == first_name 
        for w in wines
    )
    
    if not all_same_name:
        # Se i nomi sono diversi, non c'è bisogno di identificare un campo differenziante
        return None, ""
    
    # Ordine di priorità per i campi differenzianti
    # Nota: supplier non è disponibile nel modello Wine attuale
    field_priority = [
        ('vintage', 'Annata'),
        ('producer', 'Produttore'),
        ('classification', 'Classificazione'),
        ('grape_variety', 'Vitigno'),
        ('region', 'Regione'),
        ('country', 'Nazione'),
        ('wine_type', 'Tipo'),
        ('cost_price', 'Prezzo acquisto'),
        ('selling_price', 'Prezzo vendita'),
        ('alcohol_content', 'Gradazione'),
    ]
    
    # Cerca il primo campo che varia tra i vini
    for field_name, field_label in field_priority:
        # Verifica che almeno un vino abbia questo campo
        if not any(hasattr(wine, field_name) for wine in wines):
            continue
            
        values = []
        for wine in wines:
            if hasattr(wine, field_name):
                value = getattr(wine, field_name, None)
                # Normalizza valori None/vuoti
                if value is None or (isinstance(value, str) and not value.strip()):
                    value = None
                values.append(value)
            else:
                values.append(None)
        
        # Se ci sono valori diversi (non tutti None e non tutti uguali)
        unique_values = [v for v in values if v is not None]
        if len(unique_values) > 1 and len(set(str(v) for v in unique_values)) > 1:
            return field_name, field_label
    
    # Se nessun campo differenzia, ritorna None
    return None, ""


def _format_wine_button_text(wine: Any, differentiating_field: Optional[str] = None) -> str:
    """
    Formatta il testo del pulsante per un vino, evidenziando il campo differenziante se specificato.
    
    Args:
        wine: Oggetto Wine
        differentiating_field: Nome del campo che differenzia questo vino dagli altri
        
    Returns:
        Testo formattato per il pulsante
    """
    if differentiating_field and hasattr(wine, differentiating_field):
        # Mostra solo il campo differenziante
        value = getattr(wine, differentiating_field, None)
        if value is not None:
            if isinstance(value, float):
                # Per i prezzi, mostra con 2 decimali
                if differentiating_field in ['cost_price', 'selling_price']:
                    return f"{wine.name} - €{value:.2f}"
                elif differentiating_field == 'alcohol_content':
                    return f"{wine.name} - {value}%"
                else:
                    return f"{wine.name} - {value}"
            elif isinstance(value, int):
                return f"{wine.name} - {value}"
            else:
                # Stringa o altro tipo
                value_str = str(value).strip()
                if value_str:
                    return f"{wine.name} - {value_str}"
    
    # Fallback: mostra nome + produttore + annata (se disponibili)
    wine_display = wine.name
    if hasattr(wine, 'producer') and wine.producer:
        wine_display += f" ({wine.producer})"
    if hasattr(wine, 'vintage') and wine.vintage:
        wine_display += f" {wine.vintage}"
    
    return wine_display


class InventoryMovementManager:
    """Gestore movimenti inventario"""
    
    def __init__(self):
        # Usa pattern centralizzati da movement_patterns
        self.consumo_patterns = CONSUMO_PATTERNS
        self.rifornimento_patterns = RIFORNIMENTO_PATTERNS
    
    def _parse_multiple_movements(self, message_text: str, movement_type: str) -> List[Tuple[int, str]]:
        """Delega a funzione centralizzata"""
        return parse_multiple_movements(message_text, movement_type)
    
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
            context.user_data['completed_movements'] = []  # Traccia i movimenti completati per il sommario
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
            context.user_data['completed_movements'] = []  # Traccia i movimenti completati per il sommario
            # Processa il primo movimento (gli altri verranno processati dopo la selezione)
            return await self._process_rifornimento(update, context, telegram_id, multiple_rifornimenti[0][1], multiple_rifornimenti[0][0])
        
        # Usa funzione centralizzata per pattern matching
        result = parse_single_movement(message_text)
        if result:
            movement_type, quantity, wine_name = result
            logger.info(f"Matched {movement_type} pattern -> quantity={quantity}, wine={wine_name}")
            if movement_type == 'consumo':
                return await self._process_consumo(update, context, telegram_id, wine_name, quantity)
            else:
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
                # Identifica quale campo differenzia i vini
                diff_field, diff_label = _identify_differentiating_field(matching_wines)
                
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                
                if diff_field and diff_label:
                    message += f"💡 **Questi vini si differenziano per: {diff_label}**\n\n"
                
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini organizzati su più colonne
                keyboard = []
                buttons_per_row = 2  # 2 pulsanti per riga per migliore leggibilità
                
                for i in range(0, len(matching_wines), buttons_per_row):
                    row = []
                    for j in range(buttons_per_row):
                        if i + j < len(matching_wines):
                            wine = matching_wines[i + j]
                            wine_display = _format_wine_button_text(wine, diff_field)
                            
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
                # Usa funzione centralizzata per messaggio successo
                success_message = format_movement_success_message(
                    'consumo',
                    result.get('wine_name', exact_wine_name),
                    quantity,
                    result.get('quantity_before', 0),
                    result.get('quantity_after', 0)
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
                return True
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                # ✅ Se è un errore di comprensione, NON mostrare errore qui, ritorna False per passare all'AI
                if is_comprehension_error(error_msg):
                    logger.info(
                        f"[MOVEMENT] Errore comprensione in process_movement_message: '{error_msg}' - "
                        f"Ritorno False per passare all'AI"
                    )
                    return False  # ✅ Passa all'AI come fallback
                
                # Errore tecnico, mostra e termina
                error_message = format_movement_error_message(wine_name, error_msg, quantity)
                await update.message.reply_text(error_message, parse_mode='Markdown')
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
                # Identifica quale campo differenzia i vini
                diff_field, diff_label = _identify_differentiating_field(matching_wines)
                
                message = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{wine_name}'**\n\n"
                
                if diff_field and diff_label:
                    message += f"💡 **Questi vini si differenziano per: {diff_label}**\n\n"
                
                message += "Quale tra questi intendi?\n\n"
                
                # Crea pulsanti inline con i nomi completi dei vini organizzati su più colonne
                keyboard = []
                buttons_per_row = 2  # 2 pulsanti per riga per migliore leggibilità
                
                for i in range(0, len(matching_wines), buttons_per_row):
                    row = []
                    for j in range(buttons_per_row):
                        if i + j < len(matching_wines):
                            wine = matching_wines[i + j]
                            wine_display = _format_wine_button_text(wine, diff_field)
                            
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
                # Usa funzione centralizzata per messaggio successo
                success_message = format_movement_success_message(
                    'rifornimento',
                    result.get('wine_name', exact_wine_name),
                    quantity,
                    result.get('quantity_before', 0),
                    result.get('quantity_after', 0)
                )
                await update.message.reply_text(success_message, parse_mode='Markdown')
                return True
            else:
                # Gestione errori immediati
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                # ✅ Se è un errore di comprensione, NON mostrare errore qui, ritorna False per passare all'AI
                if is_comprehension_error(error_msg):
                    logger.info(
                        f"[MOVEMENT] Errore comprensione in process_movement_message: '{error_msg}' - "
                        f"Ritorno False per passare all'AI"
                    )
                    return False  # ✅ Passa all'AI come fallback
                
                # Errore tecnico, mostra e termina
                error_message = format_movement_error_message(wine_name, error_msg, quantity)
                await update.message.reply_text(error_message, parse_mode='Markdown')
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
    
    async def _show_final_summary(self, message, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Mostra un sommario finale di tutti i movimenti processati.
        """
        completed_movements = context.user_data.get('completed_movements', [])
        if not completed_movements:
            return
        
        # Raggruppa per tipo
        consumi = [m for m in completed_movements if m['type'] == 'consumo']
        rifornimenti = [m for m in completed_movements if m['type'] == 'rifornimento']
        
        summary_lines = ["📊 **Sommario Movimenti**\n"]
        
        if rifornimenti:
            summary_lines.append(f"📈 **Rifornimenti ({len(rifornimenti)}):**")
            for mov in rifornimenti:
                summary_lines.append(
                    f"  • {mov['wine_name']}: +{mov['quantity']} bottiglie "
                    f"({mov.get('quantity_before', '?')} → {mov.get('quantity_after', '?')})"
                )
            summary_lines.append("")
        
        if consumi:
            summary_lines.append(f"📉 **Consumi ({len(consumi)}):**")
            for mov in consumi:
                summary_lines.append(
                    f"  • {mov['wine_name']}: -{mov['quantity']} bottiglie "
                    f"({mov.get('quantity_before', '?')} → {mov.get('quantity_after', '?')})"
                )
            summary_lines.append("")
        
        total_movements = len(completed_movements)
        summary_lines.append(f"✅ **Totale:** {total_movements} movimenti registrati")
        
        summary_text = "\n".join(summary_lines)
        await message.reply_text(summary_text, parse_mode='Markdown')
    
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
            
            # Mostra sommario finale
            await self._show_final_summary(message, context)
            
            # Pulisci il context
            context.user_data.pop('pending_movements', None)
            context.user_data.pop('original_message', None)
            context.user_data.pop('completed_movements', None)
            return
        
        # Prendi il primo movimento dalla lista (quelli già processati sono stati rimossi)
        next_movement = pending_movements[0]
        
        logger.info(
            f"[MOVEMENT] Processando movimento multiplo pendente ({len(pending_movements)} rimanenti): "
            f"{next_movement['type']} {next_movement['quantity']} {next_movement['wine_name']}"
        )
        
        # Usa fuzzy matching migliorato (sempre attivo)
        matching_wines = await fuzzy_match_wine_name(
            telegram_id, next_movement['wine_name'], limit=50
        )
        
        if len(matching_wines) > 1:
            # Ci sono ambiguità, mostra pulsanti
            # Identifica quale campo differenzia i vini
            diff_field, diff_label = _identify_differentiating_field(matching_wines)
            
            msg_text = f"🔍 **Ho trovato {len(matching_wines)} tipologie di vini che corrispondono a '{next_movement['wine_name']}'**\n\n"
            
            if diff_field and diff_label:
                msg_text += f"💡 **Questi vini si differenziano per: {diff_label}**\n\n"
            
            msg_text += "Quale tra questi intendi?\n\n"
            
            keyboard = []
            buttons_per_row = 2
            
            for i in range(0, len(matching_wines), buttons_per_row):
                row = []
                for j in range(buttons_per_row):
                    if i + j < len(matching_wines):
                        wine = matching_wines[i + j]
                        wine_display = _format_wine_button_text(wine, diff_field)
                        
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
                msg = format_movement_success_message(
                    next_movement['type'],
                    result.get('wine_name', exact_wine_name),
                    next_movement['quantity'],
                    result.get('quantity_before', 0),
                    result.get('quantity_after', 0)
                )
                await message.reply_text(msg, parse_mode='Markdown')
                
                # Aggiungi il movimento completato alla lista per il sommario
                completed_movements = context.user_data.get('completed_movements', [])
                completed_movements.append({
                    'type': next_movement['type'],
                    'wine_name': result.get('wine_name', exact_wine_name),
                    'quantity': next_movement['quantity'],
                    'quantity_before': result.get('quantity_before'),
                    'quantity_after': result.get('quantity_after')
                })
                context.user_data['completed_movements'] = completed_movements
                
                # Rimuovi questo movimento e continua con il prossimo
                pending_movements.pop(0)
                context.user_data['pending_movements'] = pending_movements
                
                # Processa ricorsivamente il prossimo movimento
                if pending_movements:
                    await self._process_next_pending_movement(message, context, telegram_id, business_name)
                else:
                    # Tutti i movimenti completati - mostra sommario finale
                    await self._show_final_summary(message, context)
                    context.user_data.pop('pending_movements', None)
                    context.user_data.pop('original_message', None)
                    context.user_data.pop('completed_movements', None)
            else:
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                await message.reply_text(
                    f"❌ **Errore durante il processamento**\n\n{error_msg[:200]}"
                )
                # Rimuovi questo movimento dalla lista anche se fallito
                pending_movements.pop(0)
                context.user_data['pending_movements'] = pending_movements
                
                # Continua con il prossimo movimento se ce ne sono
                if pending_movements:
                    await self._process_next_pending_movement(message, context, telegram_id, business_name)
                else:
                    # Tutti i movimenti sono stati processati (anche se alcuni falliti) - mostra sommario finale
                    await self._show_final_summary(message, context)
                    context.user_data.pop('pending_movements', None)
                    context.user_data.pop('original_message', None)
                    context.user_data.pop('completed_movements', None)
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
            else:
                # Tutti i movimenti completati
                logger.info("[MOVEMENT] Tutti i movimenti multipli sono stati processati")
                context.user_data.pop('pending_movements', None)
                context.user_data.pop('original_message', None)
    
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
            
            # Controlla se ci sono movimenti multipli pendenti
            pending_movements = context.user_data.get('pending_movements', [])
            movement_to_remove = None
            
            logger.info(
                f"[MOVEMENT] Callback ricevuto: {movement_type} {quantity}, "
                f"movimenti pendenti: {len(pending_movements)}"
            )
            
            # Identifica quale movimento stiamo processando cercando nella lista
            if pending_movements:
                # Cerca il movimento corrispondente (per tipo, quantità e nome vino approssimativo)
                for mov in pending_movements:
                    if mov['type'] == movement_type and mov['quantity'] == quantity:
                        # Verifica anche che il nome vino corrisponda approssimativamente
                        if selected_wine.name.lower() in mov['wine_name'].lower() or mov['wine_name'].lower() in selected_wine.name.lower():
                            movement_to_remove = mov
                            break
                
                # Se non trovato esatto match, usa il primo movimento del tipo corretto
                if not movement_to_remove:
                    for mov in pending_movements:
                        if mov['type'] == movement_type and mov['quantity'] == quantity:
                            movement_to_remove = mov
                            break
            
            # Invia movimento al processor
            result = await processor_client.process_movement(
                telegram_id=telegram_id,
                business_name=user.business_name,
                wine_name=selected_wine.name,  # Usa il nome esatto del vino
                movement_type=movement_type,
                quantity=quantity
            )
            
            if result.get('status') == 'success':
                success_message = format_movement_success_message(
                    movement_type,
                    result.get('wine_name', selected_wine.name),
                    quantity,
                    result.get('quantity_before', 0),
                    result.get('quantity_after', 0)
                )
                await query.edit_message_text(success_message, parse_mode='Markdown')
                
                # Aggiungi il movimento completato alla lista per il sommario
                completed_movements = context.user_data.get('completed_movements', [])
                completed_movements.append({
                    'type': movement_type,
                    'wine_name': result.get('wine_name', selected_wine.name),
                    'quantity': quantity,
                    'quantity_before': result.get('quantity_before'),
                    'quantity_after': result.get('quantity_after')
                })
                context.user_data['completed_movements'] = completed_movements
                
                # Se ci sono movimenti multipli pendenti, rimuovi quello appena processato e continua
                if pending_movements:
                    # Rimuovi il movimento identificato dalla lista (se trovato)
                    if movement_to_remove and movement_to_remove in pending_movements:
                        pending_movements.remove(movement_to_remove)
                    elif pending_movements:
                        # Se non trovato esatto match, rimuovi il primo movimento del tipo corretto
                        for mov in pending_movements[:]:
                            if mov['type'] == movement_type and mov['quantity'] == quantity:
                                pending_movements.remove(mov)
                                break
                    
                    context.user_data['pending_movements'] = pending_movements
                    
                    logger.info(
                        f"[MOVEMENT] Movimento processato, rimangono {len(pending_movements)} movimenti pendenti"
                    )
                    
                    # Se ci sono ancora movimenti pendenti, processa il prossimo
                    if pending_movements:
                        # Usa query.message per inviare il prossimo messaggio
                        await self._process_next_pending_movement(
                            query.message, context, telegram_id, user.business_name
                        )
                    else:
                        # Tutti i movimenti sono stati processati - mostra sommario finale
                        await self._show_final_summary(query.message, context)
                        logger.info("[MOVEMENT] Tutti i movimenti multipli sono stati processati")
                        context.user_data.pop('pending_movements', None)
                        context.user_data.pop('original_message', None)
                        context.user_data.pop('completed_movements', None)
            else:
                error_msg = result.get('error', result.get('error_message', 'Errore sconosciuto'))
                
                error_message = format_movement_error_message(selected_wine.name, error_msg, quantity)
                await query.edit_message_text(error_message, parse_mode='Markdown')
            
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
