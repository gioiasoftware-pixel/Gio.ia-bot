"""
Gestione movimenti inventario (consumi e rifornimenti)
"""
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database import db_manager

logger = logging.getLogger(__name__)

class InventoryMovementManager:
    """Gestore movimenti inventario"""
    
    def __init__(self):
        # Pattern per riconoscere movimenti
        self.consumo_patterns = [
            r'ho venduto (\d+) bottiglie? di (.+)',
            r'ho consumato (\d+) bottiglie? di (.+)',
            r'ho bevuto (\d+) bottiglie? di (.+)',
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
            r'ricevuto (\d+) (.+)',
            r'comprato (\d+) (.+)',
            r'aggiunto (\d+) (.+)',
            r'(\d+) bottiglie? di (.+) ricevute?',
            r'(\d+) bottiglie? di (.+) comprate?',
            r'(\d+) bottiglie? di (.+) aggiunte?'
        ]
    
    def process_movement_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Processa un messaggio per riconoscere movimenti inventario"""
        user = update.effective_user
        telegram_id = user.id
        message_text = update.message.text.lower().strip()
        
        # Verifica se l'onboarding è completato
        if not db_manager.get_user_by_telegram_id(telegram_id) or not db_manager.get_user_by_telegram_id(telegram_id).onboarding_completed:
            return False
        
        # Cerca pattern di consumo
        for pattern in self.consumo_patterns:
            match = re.search(pattern, message_text)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                return self._process_consumo(update, context, telegram_id, wine_name, quantity)
        
        # Cerca pattern di rifornimento
        for pattern in self.rifornimento_patterns:
            match = re.search(pattern, message_text)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                return self._process_rifornimento(update, context, telegram_id, wine_name, quantity)
        
        return False
    
    def _process_consumo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                        telegram_id: int, wine_name: str, quantity: int) -> bool:
        """Processa un consumo (quantità negativa)"""
        try:
            # Trova il vino nell'inventario
            wines = db_manager.get_user_wines(telegram_id)
            matching_wine = self._find_matching_wine(wines, wine_name)
            
            if not matching_wine:
                update.message.reply_text(
                    f"❌ **Vino non trovato**\n\n"
                    f"Non ho trovato '{wine_name}' nel tuo inventario.\n"
                    f"💡 Controlla il nome o usa `/inventario` per vedere i vini disponibili."
                )
                return True
            
            # Verifica quantità disponibile
            if matching_wine.quantity < quantity:
                update.message.reply_text(
                    f"⚠️ **Quantità insufficiente**\n\n"
                    f"**{matching_wine.name}** ({matching_wine.producer})\n"
                    f"📦 Disponibili: {matching_wine.quantity} bottiglie\n"
                    f"🍷 Richieste: {quantity} bottiglie\n\n"
                    f"💡 Verifica la quantità o aggiorna l'inventario."
                )
                return True
            
            # Aggiorna quantità e crea log
            success = db_manager.update_wine_quantity_with_log(
                telegram_id=telegram_id,
                wine_name=matching_wine.name,
                quantity_change=-quantity,  # Negativo per consumo
                movement_type="consumo",
                notes=f"Vendita/consumo di {quantity} bottiglie"
            )
            
            if success:
                new_quantity = matching_wine.quantity - quantity
                success_message = (
                    f"✅ **Consumo registrato**\n\n"
                    f"🍷 **Vino:** {matching_wine.name}\n"
                    f"🏭 **Produttore:** {matching_wine.producer}\n"
                    f"📦 **Quantità:** {matching_wine.quantity} → {new_quantity} bottiglie\n"
                    f"📉 **Consumate:** {quantity} bottiglie\n\n"
                    f"💾 **Log salvato** nel sistema"
                )
                update.message.reply_text(success_message, parse_mode='Markdown')
            else:
                update.message.reply_text("❌ Errore durante l'aggiornamento. Riprova.")
            
            return True
            
        except Exception as e:
            logger.error(f"Errore processamento consumo: {e}")
            update.message.reply_text("❌ Errore durante il processamento. Riprova.")
            return True
    
    def _process_rifornimento(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                             telegram_id: int, wine_name: str, quantity: int) -> bool:
        """Processa un rifornimento (quantità positiva)"""
        try:
            # Trova il vino nell'inventario
            wines = db_manager.get_user_wines(telegram_id)
            matching_wine = self._find_matching_wine(wines, wine_name)
            
            if not matching_wine:
                update.message.reply_text(
                    f"❌ **Vino non trovato**\n\n"
                    f"Non ho trovato '{wine_name}' nel tuo inventario.\n"
                    f"💡 Controlla il nome o usa `/inventario` per vedere i vini disponibili.\n\n"
                    f"🆕 **Per aggiungere un nuovo vino:** usa `/aggiungi`"
                )
                return True
            
            # Aggiorna quantità e crea log
            success = db_manager.update_wine_quantity_with_log(
                telegram_id=telegram_id,
                wine_name=matching_wine.name,
                quantity_change=quantity,  # Positivo per rifornimento
                movement_type="rifornimento",
                notes=f"Rifornimento di {quantity} bottiglie"
            )
            
            if success:
                new_quantity = matching_wine.quantity + quantity
                success_message = (
                    f"✅ **Rifornimento registrato**\n\n"
                    f"🍷 **Vino:** {matching_wine.name}\n"
                    f"🏭 **Produttore:** {matching_wine.producer}\n"
                    f"📦 **Quantità:** {matching_wine.quantity} → {new_quantity} bottiglie\n"
                    f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                    f"💾 **Log salvato** nel sistema"
                )
                update.message.reply_text(success_message, parse_mode='Markdown')
            else:
                update.message.reply_text("❌ Errore durante l'aggiornamento. Riprova.")
            
            return True
            
        except Exception as e:
            logger.error(f"Errore processamento rifornimento: {e}")
            update.message.reply_text("❌ Errore durante il processamento. Riprova.")
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
    
    def show_movement_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          days: int = 7) -> None:
        """Mostra i log dei movimenti"""
        user = update.effective_user
        telegram_id = user.id
        
        logs = db_manager.get_inventory_logs(telegram_id, limit=50)
        
        if not logs:
            update.message.reply_text(
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
            update.message.reply_text(
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
        
        update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    def get_daily_summary(self, telegram_id: int, date: datetime = None) -> Dict[str, Any]:
        """Ottieni riassunto giornaliero dei movimenti"""
        if date is None:
            date = datetime.utcnow()
        
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
        
        logs = db_manager.get_inventory_logs(telegram_id, limit=1000)
        
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
