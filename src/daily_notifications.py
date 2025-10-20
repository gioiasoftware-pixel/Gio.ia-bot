"""
Sistema notifiche giornaliere per Gio.ia-bot
"""
import logging
import asyncio
from datetime import datetime, time, timedelta
from typing import List, Dict, Any
from telegram import Bot
from .database import db_manager
from .inventory_movements import inventory_movement_manager

logger = logging.getLogger(__name__)

class DailyNotificationManager:
    """Gestore notifiche giornaliere"""
    
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)
        self.notification_time = time(21, 0)  # 21:00 ogni giorno
    
    async def send_daily_summary(self, telegram_id: int) -> bool:
        """Invia riassunto giornaliero a un utente"""
        try:
            # Ottieni riassunto giornaliero
            summary = inventory_movement_manager.get_daily_summary(telegram_id)
            
            if summary['total_movements'] == 0:
                # Nessun movimento oggi
                message = (
                    f"📅 **Riassunto Giornaliero - {summary['date']}**\n\n"
                    f"😴 **Nessun movimento registrato oggi**\n\n"
                    f"💡 **Ricorda:** Comunica i consumi e rifornimenti per tenere l'inventario aggiornato!\n\n"
                    f"📋 **Esempi:**\n"
                    f"• 'Ho venduto 2 bottiglie di Chianti'\n"
                    f"• 'Ho ricevuto 10 bottiglie di Barolo'"
                )
            else:
                # Movimenti registrati
                message = (
                    f"📅 **Riassunto Giornaliero - {summary['date']}**\n\n"
                    f"📊 **Movimenti totali:** {summary['total_movements']}\n"
                    f"📉 **Consumi:** {summary['consumi_count']} movimenti\n"
                    f"📈 **Rifornimenti:** {summary['rifornimenti_count']} movimenti\n\n"
                )
                
                if summary['total_consumed'] > 0:
                    message += f"🍷 **Bottiglie consumate:** {summary['total_consumed']}\n"
                
                if summary['total_received'] > 0:
                    message += f"📦 **Bottiglie ricevute:** {summary['total_received']}\n"
                
                message += "\n💾 **Tutti i movimenti sono stati registrati nel sistema**"
            
            # Invia messaggio
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Riassunto giornaliero inviato a {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Errore invio riassunto giornaliero a {telegram_id}: {e}")
            return False
    
    async def send_low_stock_alert(self, telegram_id: int) -> bool:
        """Invia alert per scorte basse"""
        try:
            # Ottieni vini con scorte basse
            wines = db_manager.get_user_wines(telegram_id)
            low_stock_wines = [w for w in wines if w.quantity <= w.min_quantity]
            
            if not low_stock_wines:
                return False  # Nessun alert da inviare
            
            message = "⚠️ **ALERT: Scorte Basse**\n\n"
            message += "I seguenti vini hanno scorte basse:\n\n"
            
            for wine in low_stock_wines[:10]:  # Max 10 vini
                message += f"🍷 **{wine.name}** ({wine.producer})\n"
                message += f"📦 Disponibili: {wine.quantity} (min: {wine.min_quantity})\n\n"
            
            if len(low_stock_wines) > 10:
                message += f"... e altri {len(low_stock_wines) - 10} vini\n\n"
            
            message += "💡 **Raccomandazione:** Considera di riordinare questi vini!"
            
            # Invia messaggio
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Alert scorte basse inviato a {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Errore invio alert scorte basse a {telegram_id}: {e}")
            return False
    
    async def send_weekly_report(self, telegram_id: int) -> bool:
        """Invia report settimanale"""
        try:
            # Ottieni dati ultima settimana
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
            
            # Ottieni tutti i log della settimana
            logs = db_manager.get_inventory_logs(telegram_id, limit=1000)
            weekly_logs = [
                log for log in logs 
                if start_date <= log['movement_date'] <= end_date
            ]
            
            if not weekly_logs:
                return False  # Nessun movimento questa settimana
            
            # Analizza i dati
            consumi = [log for log in weekly_logs if log['movement_type'] == 'consumo']
            rifornimenti = [log for log in weekly_logs if log['movement_type'] == 'rifornimento']
            
            # Vini più venduti
            wine_sales = {}
            for log in consumi:
                wine_name = log['wine_name']
                if wine_name not in wine_sales:
                    wine_sales[wine_name] = 0
                wine_sales[wine_name] += abs(log['quantity_change'])
            
            top_selling = sorted(wine_sales.items(), key=lambda x: x[1], reverse=True)[:5]
            
            message = (
                f"📊 **Report Settimanale**\n"
                f"📅 {start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')}\n\n"
                f"📈 **Statistiche:**\n"
                f"• Movimenti totali: {len(weekly_logs)}\n"
                f"• Consumi: {len(consumi)}\n"
                f"• Rifornimenti: {len(rifornimenti)}\n"
                f"• Bottiglie vendute: {sum(abs(log['quantity_change']) for log in consumi)}\n"
                f"• Bottiglie ricevute: {sum(log['quantity_change'] for log in rifornimenti)}\n\n"
            )
            
            if top_selling:
                message += "🏆 **Top 5 Vini Venduti:**\n"
                for i, (wine_name, quantity) in enumerate(top_selling, 1):
                    message += f"{i}. {wine_name}: {quantity} bottiglie\n"
                message += "\n"
            
            message += "💡 **Suggerimento:** Usa questi dati per ottimizzare il tuo inventario!"
            
            # Invia messaggio
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Report settimanale inviato a {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Errore invio report settimanale a {telegram_id}: {e}")
            return False
    
    async def send_all_daily_summaries(self) -> None:
        """Invia riassunti giornalieri a tutti gli utenti"""
        try:
            # Ottieni tutti gli utenti con onboarding completato
            users = db_manager.get_all_users()
            active_users = [user for user in users if user.onboarding_completed]
            
            logger.info(f"Invio riassunti giornalieri a {len(active_users)} utenti")
            
            for user in active_users:
                try:
                    await self.send_daily_summary(user.telegram_id)
                    await asyncio.sleep(1)  # Pausa tra invii
                except Exception as e:
                    logger.error(f"Errore invio a utente {user.telegram_id}: {e}")
            
            logger.info("Invio riassunti giornalieri completato")
            
        except Exception as e:
            logger.error(f"Errore invio riassunti giornalieri: {e}")
    
    async def send_all_low_stock_alerts(self) -> None:
        """Invia alert scorte basse a tutti gli utenti"""
        try:
            # Ottieni tutti gli utenti con onboarding completato
            users = db_manager.get_all_users()
            active_users = [user for user in users if user.onboarding_completed]
            
            logger.info(f"Controllo scorte basse per {len(active_users)} utenti")
            
            for user in active_users:
                try:
                    await self.send_low_stock_alert(user.telegram_id)
                    await asyncio.sleep(1)  # Pausa tra invii
                except Exception as e:
                    logger.error(f"Errore controllo scorte per utente {user.telegram_id}: {e}")
            
            logger.info("Controllo scorte basse completato")
            
        except Exception as e:
            logger.error(f"Errore controllo scorte basse: {e}")
    
    async def start_daily_scheduler(self) -> None:
        """Avvia il scheduler giornaliero"""
        logger.info("Scheduler notifiche giornaliere avviato")
        
        while True:
            try:
                now = datetime.utcnow()
                current_time = now.time()
                
                # Se è l'ora delle notifiche
                if current_time.hour == self.notification_time.hour and current_time.minute == self.notification_time.minute:
                    logger.info("Invio notifiche giornaliere...")
                    
                    # Invia riassunti giornalieri
                    await self.send_all_daily_summaries()
                    
                    # Invia alert scorte basse
                    await self.send_all_low_stock_alerts()
                    
                    # Aspetta un minuto per evitare invii multipli
                    await asyncio.sleep(60)
                
                # Controlla ogni minuto
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Errore scheduler notifiche: {e}")
                await asyncio.sleep(60)  # Riprova tra un minuto

# Funzione per avviare il scheduler (da chiamare nel main)
async def start_notification_scheduler(bot_token: str) -> None:
    """Avvia il sistema di notifiche"""
    notification_manager = DailyNotificationManager(bot_token)
    await notification_manager.start_daily_scheduler()
