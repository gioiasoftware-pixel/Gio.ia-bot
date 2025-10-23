"""
Nuovo sistema di onboarding per Gio.ia-bot
Flusso: Upload file -> Nome utente -> Nome locale -> Backup inventario
"""
import json
import logging
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database import db_manager
from .file_upload import file_upload_manager

logger = logging.getLogger(__name__)

class NewOnboardingManager:
    """Nuovo gestore onboarding con flusso specifico"""
    
    def __init__(self):
        self.onboarding_steps = {
            'upload_file': {
                'question': "📤 **Benvenuto in Gio.ia-bot!**\n\nPrima di tutto, carica il file del tuo inventario iniziale.\n\n📋 **Formati supportati:**\n• CSV (.csv)\n• Excel (.xlsx, .xls)\n• Foto/Immagine (.jpg, .png)\n\n💡 **Intestazione CSV richiesta:**\nEtichetta, Produttore, Uvaggio, Comune, Regione, Nazione, Fornitore, Costo, Prezzo in carta, Quantità in magazzino, Annata, Note, Denominazione, Formato, Alcol, Codice\n\n📷 **Per le foto:** Invia una foto chiara dell'inventario e userò l'OCR per estrarre i dati.",
                'field': 'inventory_file'
            },
            'username': {
                'question': "👤 **Nome utente**\n\nCome vuoi essere chiamato nel sistema?\nEsempio: 'Mario', 'Chef Rossi', 'Admin'",
                'field': 'username'
            },
            'restaurant_name': {
                'question': "🏢 **Nome del locale**\n\nQual è il nome del tuo ristorante/enoteca?\nEsempio: 'Ristorante da Mario', 'Enoteca del Borgo'",
                'field': 'restaurant_name'
            }
        }
    
    async def start_new_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il nuovo processo di onboarding guidato dall'AI"""
        user = update.effective_user
        telegram_id = user.id
        
        logger.info(f"Nuovo onboarding AI avviato per: {user.username} (ID: {telegram_id})")
        
        # Crea utente se non esiste
        existing_user = db_manager.get_user_by_telegram_id(telegram_id)
        if not existing_user:
            db_manager.create_user(
                telegram_id=telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
        
        # Avvia onboarding guidato dall'AI
        await self._start_ai_guided_onboarding(update, context)
    
    def _send_onboarding_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE, step: str) -> None:
        """Invia un step dell'onboarding"""
        step_data = self.onboarding_steps[step]
        question = step_data['question']
        
        # Salva lo step corrente
        context.user_data['onboarding_step'] = step
        
        # Invia messaggio
        update.message.reply_text(question, parse_mode='Markdown')
    
    def handle_onboarding_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le risposte durante l'onboarding"""
        if 'onboarding_step' not in context.user_data:
            return False
        
        current_step = context.user_data['onboarding_step']
        
        if current_step == 'username':
            # Salva il nome utente
            username = update.message.text.strip()
            context.user_data['onboarding_data'] = context.user_data.get('onboarding_data', {})
            context.user_data['onboarding_data']['username'] = username
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'restaurant_name')
            return True
        
        elif current_step == 'restaurant_name':
            # Salva il nome del locale
            restaurant_name = update.message.text.strip()
            context.user_data['onboarding_data']['restaurant_name'] = restaurant_name
            
            # Completa l'onboarding
            self._complete_onboarding(update, context)
            return True
        
        return False
    
    def handle_file_upload_during_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                           file_type: str, file_data: bytes) -> bool:
        """Gestisce l'upload di file durante l'onboarding"""
        if context.user_data.get('onboarding_step') != 'upload_file':
            return False
        
        try:
            # Processa il file
            if file_type == 'csv':
                wines_data = file_upload_manager._process_csv(file_data)
            elif file_type == 'excel':
                wines_data = file_upload_manager._process_excel(file_data)
            elif file_type == 'photo':
                wines_data = file_upload_manager._process_photo_ocr(file_data)
            else:
                return False
            
            if not wines_data:
                update.message.reply_text(
                    "❌ **Errore nel file**\n\n"
                    "Il file non contiene dati validi o l'intestazione non è corretta.\n"
                    "Riprova con un file valido."
                )
                return True
            
            # Salva i dati temporaneamente
            context.user_data['uploaded_wines'] = wines_data
            context.user_data['onboarding_data'] = context.user_data.get('onboarding_data', {})
            
            # Conferma upload
            success_message = (
                f"✅ **File caricato con successo!**\n\n"
                f"📊 **Risultati:**\n"
                f"• Vini estratti: {len(wines_data)}\n"
                f"• File processato correttamente\n\n"
                f"🎯 **Prossimo step:** Configurazione profilo utente"
            )
            update.message.reply_text(success_message, parse_mode='Markdown')
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'username')
            return True
            
        except Exception as e:
            logger.error(f"Errore processamento file durante onboarding: {e}")
            update.message.reply_text(
                "❌ **Errore durante il processamento**\n\n"
                "Si è verificato un errore durante l'elaborazione del file.\n"
                "Riprova con un file valido."
            )
            return True
    
    def _complete_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Completa il processo di onboarding"""
        user = update.effective_user
        telegram_id = user.id
        onboarding_data = context.user_data.get('onboarding_data', {})
        uploaded_wines = context.user_data.get('uploaded_wines', [])
        
        try:
            # Aggiorna dati utente
            success = db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                business_name=onboarding_data.get('restaurant_name'),
                onboarding_completed=True
            )
            
            if not success:
                update.message.reply_text("❌ Errore durante il salvataggio. Riprova con `/start`.")
                return
            
            # Salva i vini nel database
            saved_count = 0
            for wine_data in uploaded_wines:
                try:
                    wine = db_manager.add_wine(telegram_id, wine_data)
                    if wine:
                        saved_count += 1
                except Exception as e:
                    logger.error(f"Errore salvataggio vino: {e}")
            
            # Crea backup dell'inventario iniziale
            backup_data = json.dumps(uploaded_wines, ensure_ascii=False, indent=2)
            db_manager.create_inventory_backup(
                telegram_id=telegram_id,
                backup_name="Inventario Iniziale",
                backup_data=backup_data,
                backup_type="initial"
            )
            
            # Messaggio di completamento
            completion_text = (
                f"🎉 **Onboarding completato con successo!**\n\n"
                f"👤 **Utente:** {onboarding_data.get('username', 'N/A')}\n"
                f"🏢 **Locale:** {onboarding_data.get('restaurant_name', 'N/A')}\n"
                f"📦 **Inventario:** {saved_count} vini caricati\n"
                f"💾 **Backup:** Inventario iniziale salvato\n\n"
                f"🚀 **Il tuo sistema è pronto!**\n\n"
                f"📋 **Come usare il bot:**\n"
                f"• Scrivi i consumi: 'Ho venduto 2 bottiglie di Chianti'\n"
                f"• Aggiungi rifornimenti: 'Ho ricevuto 10 bottiglie di Barolo'\n"
                f"• Chiedi report: 'Fammi un report del mio inventario'\n"
                f"• Vedi log: 'Mostrami i movimenti di oggi'\n\n"
                f"💡 **Suggerimento:** Comunica i movimenti a fine giornata o in tempo reale per tenere l'inventario sempre aggiornato!"
            )
            
            update.message.reply_text(completion_text, parse_mode='Markdown')
            
            # Pulisci i dati temporanei
            context.user_data.pop('onboarding_step', None)
            context.user_data.pop('onboarding_data', None)
            context.user_data.pop('uploaded_wines', None)
            
            logger.info(f"Onboarding completato per utente {telegram_id}")
            
        except Exception as e:
            logger.error(f"Errore completamento onboarding: {e}")
            update.message.reply_text("❌ Errore durante il completamento. Riprova con `/start`.")
    
    async def _start_ai_guided_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia onboarding guidato dall'AI"""
        from .ai import get_ai_response
        
        # Messaggio di benvenuto con AI
        welcome_message = (
            "🎉 **Benvenuto in Gio.ia-bot!**\n\n"
            "Sono il tuo assistente AI per la gestione inventario vini. "
            "Ti guiderò passo dopo passo per configurare il tuo sistema.\n\n"
            "**Prima cosa importante:** Ho bisogno del tuo inventario iniziale per creare il backup del giorno 0.\n\n"
            "📤 **Carica il file del tuo inventario** (CSV, Excel o foto) e iniziamo!"
        )
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
        
        # Imposta stato onboarding
        context.user_data['onboarding_step'] = 'ai_guided'
        context.user_data['onboarding_data'] = {}
        
        logger.info("Onboarding AI guidato avviato")
    
    def handle_ai_guided_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le risposte durante l'onboarding guidato dall'AI"""
        from .ai import get_ai_response
        
        if context.user_data.get('onboarding_step') != 'ai_guided':
            return False
        
        user_text = update.message.text
        telegram_id = update.effective_user.id
        
        # Usa AI per guidare l'onboarding
        ai_prompt = f"""
        Sei Gio.ia-bot durante l'onboarding di un nuovo utente. 
        L'utente ha scritto: "{user_text}"
        
        GUIDA L'ONBOARDING:
        1. Se l'utente carica un file inventario, conferma e procedi
        2. Se l'utente fornisce nome utente/locale, salva e procedi
        3. Se l'utente fa domande, rispondi e guida al prossimo step
        4. Sii sempre gentile e professionale
        5. Mantieni il focus sull'onboarding
        
        STATO ATTUALE: Onboarding in corso
        PROSSIMO STEP: Carica inventario iniziale
        """
        
        # Ottieni risposta AI
        ai_response = get_ai_response(ai_prompt, telegram_id)
        
        # Invia risposta AI
        update.message.reply_text(ai_response)
        
        return True
    
    def is_onboarding_complete(self, telegram_id: int) -> bool:
        """Verifica se l'onboarding è completato"""
        user = db_manager.get_user_by_telegram_id(telegram_id)
        return user and user.onboarding_completed if user else False

# Istanza globale del nuovo gestore onboarding
new_onboarding_manager = NewOnboardingManager()
