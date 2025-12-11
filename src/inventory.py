"""
Gestione inventario vini
"""
import logging
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database_async import async_db_manager
from .database_async import Wine  # Solo per modello tipo

logger = logging.getLogger(__name__)

class InventoryManager:
    """Gestore dell'inventario vini"""
    
    def __init__(self):
        self.wine_types = [
            "🍷 Rosso", "🥂 Bianco", "🌸 Rosato", 
            "🍾 Spumante", "🍸 Liquore", "🍺 Birra", "🥃 Distillato"
        ]
        
        self.classifications = [
            "DOCG", "DOC", "IGT", "VdT", "IGP", "AOC", "AOP", "VQA", "Altro"
        ]
    
    async def show_inventory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra l'inventario dell'utente"""
        user = update.effective_user
        telegram_id = user.id
        
        wines = await async_db_manager.get_user_wines(telegram_id)
        # Calcola stats localmente
        stats = {
            'total_wines': len(wines),
            'total_quantity': sum(w.quantity or 0 for w in wines),
            'low_stock_count': len([w for w in wines if (w.quantity or 0) <= (getattr(w, 'min_quantity', 0) or 0)])
        }
        
        if not wines:
            message = (
                "📦 **Il tuo inventario è vuoto**\n\n"
                "💡 Inizia aggiungendo il tuo primo vino con il comando `/aggiungi`\n"
                "o chiedi all'AI di aiutarti a gestire l'inventario!"
            )
            await update.message.reply_text(message, parse_mode='Markdown')
            return
        
        # Header con statistiche
        header = (
            f"📊 **Inventario - {stats['total_wines']} vini**\n"
            f"📦 **Quantità totale:** {stats['total_quantity']} bottiglie\n"
            f"⚠️ **Scorte basse:** {stats['low_stock_count']} vini\n\n"
        )
        
        # Lista vini
        wine_list = []
        for i, wine in enumerate(wines[:10], 1):  # Mostra max 10 vini
            min_qty = getattr(wine, 'min_quantity', 0) or 0
            qty = wine.quantity or 0
            status_emoji = "⚠️" if qty <= min_qty else "✅"
            wine_info = (
                f"{i}. {status_emoji} **{wine.name}**\n"
                f"   🏷️ {wine.producer or 'Produttore sconosciuto'}\n"
                f"   📅 {wine.vintage or 'N/A'}\n"
                f"   📦 Quantità: {wine.quantity} bottiglie\n"
                f"   💰 Prezzo: €{wine.selling_price or 'N/A'}\n"
            )
            wine_list.append(wine_info)
        
        message = header + "\n".join(wine_list)
        
        if len(wines) > 10:
            message += f"\n... e altri {len(wines) - 10} vini"
        
        # Aggiungi pulsanti per azioni
        keyboard = [
            [InlineKeyboardButton("➕ Aggiungi vino", callback_data="add_wine")],
            [InlineKeyboardButton("📊 Report completo", callback_data="full_report")],
            [InlineKeyboardButton("⚠️ Scorte basse", callback_data="low_stock")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def start_add_wine(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il processo di aggiunta vino"""
        context.user_data['adding_wine'] = True
        context.user_data['wine_data'] = {}
        
        message = (
            "🍷 **Aggiungi un nuovo vino**\n\n"
            "📝 Iniziamo con il nome del vino:\n"
            "Esempio: 'Chianti Classico' o 'Barolo 2018'"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def handle_wine_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce l'inserimento dati vino"""
        if not context.user_data.get('adding_wine', False):
            return False
        
        wine_data = context.user_data.get('wine_data', {})
        current_step = context.user_data.get('wine_step', 'name')
        
        if current_step == 'name':
            wine_data['name'] = update.message.text.strip()
            context.user_data['wine_data'] = wine_data
            context.user_data['wine_step'] = 'producer'
            
            await update.message.reply_text(
                "🏭 **Produttore:**\n"
                "Esempio: 'Antinori' o 'Gaja'"
            )
            return True
        
        elif current_step == 'producer':
            wine_data['producer'] = update.message.text.strip()
            context.user_data['wine_data'] = wine_data
            context.user_data['wine_step'] = 'vintage'
            
            await update.message.reply_text(
                "📅 **Annata:**\n"
                "Esempio: '2020' o 'N/A' se non specificata"
            )
            return True
        
        elif current_step == 'vintage':
            vintage_text = update.message.text.strip()
            if vintage_text.lower() in ['n/a', 'na', 'non specificata']:
                wine_data['vintage'] = None
            else:
                try:
                    wine_data['vintage'] = int(vintage_text)
                except ValueError:
                    wine_data['vintage'] = None
            
            context.user_data['wine_data'] = wine_data
            context.user_data['wine_step'] = 'type'
            
            # Mostra tastiera per tipo vino
            keyboard = []
            for i in range(0, len(self.wine_types), 2):
                row = []
                for j in range(2):
                    if i + j < len(self.wine_types):
                        wine_type = self.wine_types[i + j]
                        row.append(InlineKeyboardButton(wine_type, callback_data=f"wine_type_{i+j}"))
                keyboard.append(row)
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "🍷 **Tipo di vino:**",
                reply_markup=reply_markup
            )
            return True
        
        elif current_step == 'quantity':
            try:
                quantity = int(update.message.text.strip())
                wine_data['quantity'] = quantity
                context.user_data['wine_data'] = wine_data
                
                # Completa l'aggiunta - ASYNC
                await self._complete_wine_addition(update, context)
                return True
            except ValueError:
                await update.message.reply_text("❌ Inserisci un numero valido per la quantità.")
                return True
        
        return False
    
    async def handle_wine_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le callback per l'aggiunta vino"""
        query = update.callback_query
        await query.answer()
        
        if not context.user_data.get('adding_wine', False):
            return False
        
        if query.data.startswith('wine_type_'):
            # Tipo di vino selezionato
            type_index = int(query.data.split('_')[2])
            wine_type = self.wine_types[type_index].split(' ', 1)[1]  # Rimuovi emoji
            
            wine_data = context.user_data.get('wine_data', {})
            wine_data['wine_type'] = wine_type
            context.user_data['wine_data'] = wine_data
            context.user_data['wine_step'] = 'quantity'
            
            await query.edit_message_text(
                "📦 **Quantità in magazzino:**\n"
                "Quante bottiglie hai di questo vino?"
            )
            return True
        
        return False
    
    async def _complete_wine_addition(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Completa l'aggiunta del vino"""
        user = update.effective_user
        telegram_id = user.id
        wine_data = context.user_data.get('wine_data', {})
        
        # Aggiungi il vino al database - ASYNC
        wine = await async_db_manager.add_wine(telegram_id, wine_data)
        
        if wine:
            success_message = (
                f"✅ **Vino aggiunto con successo!**\n\n"
                f"🍷 **Nome:** {wine.name}\n"
                f"🏭 **Produttore:** {wine.producer or 'N/A'}\n"
                f"📅 **Annata:** {wine.vintage or 'N/A'}\n"
                f"🍷 **Tipo:** {wine.wine_type or 'N/A'}\n"
                f"📦 **Quantità:** {wine.quantity} bottiglie\n\n"
                "💡 Usa `/view` per vedere il tuo inventario completo!"
            )
            await update.message.reply_text(success_message, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Errore durante l'aggiunta del vino. Riprova.")
        
        # Pulisci i dati temporanei
        context.user_data.pop('adding_wine', None)
        context.user_data.pop('wine_data', None)
        context.user_data.pop('wine_step', None)
    
    async def show_low_stock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra vini con scorte basse"""
        user = update.effective_user
        telegram_id = user.id
        
        low_stock_wines = await async_db_manager.get_low_stock_wines(telegram_id)
        
        if not low_stock_wines:
            message = "✅ **Tutte le scorte sono a posto!**\n\nNon hai vini con scorte basse."
            await update.message.reply_text(message, parse_mode='Markdown')
            return
        
        message = f"⚠️ **Scorte basse - {len(low_stock_wines)} vini**\n\n"
        
        for wine in low_stock_wines:
            message += (
                f"🍷 **{wine.name}**\n"
                f"   📦 Quantità: {wine.quantity} (min: {wine.min_quantity})\n"
                f"   🏭 {wine.producer or 'Produttore sconosciuto'}\n\n"
            )
        
        message += "💡 Considera di riordinare questi vini!"
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def get_inventory_summary(self, telegram_id: int) -> Dict[str, Any]:
        """Ottieni un riassunto dell'inventario per l'AI"""
        wines = await async_db_manager.get_user_wines(telegram_id)
        stats = {
            'total_wines': len(wines),
            'total_quantity': sum(w.quantity or 0 for w in wines),
            'low_stock_count': len([w for w in wines if (w.quantity or 0) <= (getattr(w, 'min_quantity', 0) or 0)])
        }
        
        wine_summary = []
        for wine in wines:
            wine_info = {
                'name': wine.name,
                'producer': wine.producer,
                'vintage': wine.vintage,
                'type': wine.wine_type,
                'quantity': wine.quantity,
                'min_quantity': wine.min_quantity,
                'selling_price': wine.selling_price,
                'low_stock': wine.quantity <= wine.min_quantity
            }
            wine_summary.append(wine_info)
        
        return {
            'total_wines': stats['total_wines'],
            'total_quantity': stats['total_quantity'],
            'low_stock_count': stats['low_stock_count'],
            'wines': wine_summary
        }

# Istanza globale del gestore inventario
inventory_manager = InventoryManager()
