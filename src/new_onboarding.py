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
            # Salva i dati temporaneamente per l'onboarding
            context.user_data['uploaded_wines'] = []  # Dati vuoti, elaborazione nel processor
            context.user_data['onboarding_data'] = context.user_data.get('onboarding_data', {})
            
            # Conferma upload
            success_message = (
                f"✅ **File caricato con successo!**\n\n"
                f"📊 **File ricevuto:** {file_type.upper()}\n"
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
            
            # I vini sono già stati salvati dal processor
            # Non serve salvarli di nuovo qui
            saved_count = 0  # Il processor ha già salvato tutto
            
            # Messaggio di completamento
            completion_text = (
                f"🎉 **Onboarding completato con successo!**\n\n"
                f"👤 **Utente:** {onboarding_data.get('username', 'N/A')}\n"
                f"🏢 **Locale:** {onboarding_data.get('restaurant_name', 'N/A')}\n"
                f"📦 **Inventario:** Elaborato e salvato dal sistema\n"
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
            context.user_data.pop('inventory_file', None)
            context.user_data.pop('inventory_photo', None)
            
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
            "**Prima cosa:** Ho bisogno di sapere il nome del tuo locale per personalizzare il sistema.\n\n"
            "🏢 **Come si chiama il tuo ristorante/enoteca?**"
        )
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
        
        # Imposta stato onboarding
        context.user_data['onboarding_step'] = 'ai_guided'
        context.user_data['onboarding_data'] = {}
        
        logger.info("Onboarding AI guidato avviato")
    
    async def handle_ai_guided_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le risposte durante l'onboarding guidato dall'AI"""
        from .ai import get_ai_response
        from .file_upload import file_upload_manager
        
        if context.user_data.get('onboarding_step') != 'ai_guided':
            return False
        
        telegram_id = update.effective_user.id
        user_data = context.user_data.get('onboarding_data', {})
        
        # Gestisci risposta testuale (nome locale) PRIMA
        if update.message.text:
            await self._handle_business_name_response(update, context)
            return True
        
        # Gestisci upload file inventario DOPO aver ricevuto il nome
        if update.message.document:
            await self._handle_inventory_upload(update, context)
            return True
        
        # Gestisci foto inventario DOPO aver ricevuto il nome
        if update.message.photo:
            await self._handle_inventory_photo(update, context)
            return True
        
        return False
    
    async def _handle_business_name_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce la risposta del nome del locale"""
        telegram_id = update.effective_user.id
        business_name = update.message.text.strip()
        
        # Salva il nome del locale
        context.user_data['onboarding_data'] = context.user_data.get('onboarding_data', {})
        context.user_data['onboarding_data']['business_name'] = business_name
        
        # Conferma e chiedi il file inventario
        await update.message.reply_text(
            f"✅ **Perfetto! {business_name}** configurato!\n\n"
            f"📋 Ora ho bisogno del tuo inventario iniziale per creare il backup del giorno 0.\n\n"
            f"📤 **Carica il file del tuo inventario** (CSV, Excel o foto) e iniziamo!"
        )
        
        # Imposta stato per ricevere file
        context.user_data['onboarding_step'] = 'waiting_inventory_file'
        
        logger.info(f"Nome locale ricevuto da {telegram_id}: {business_name}")
    
    async def _handle_inventory_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce l'upload del file inventario"""
        from .ai import get_ai_response
        
        telegram_id = update.effective_user.id
        document = update.message.document
        business_name = context.user_data.get('onboarding_data', {}).get('business_name', 'Temporaneo')
        
        # Ringrazia per il file
        await update.message.reply_text(
            f"✅ **Perfetto! File inventario ricevuto!**\n\n"
            f"📋 Sto elaborando l'inventario di **{business_name}** per creare il backup del giorno 0...\n\n"
            f"🔄 **Elaborazione in corso...**"
        )
        
        # Salva il file per l'elaborazione
        context.user_data['inventory_file'] = {
            'file_id': document.file_id,
            'file_name': document.file_name,
            'file_size': document.file_size
        }
        
        logger.info(f"File inventario ricevuto da {telegram_id}: {document.file_name}")
        
        # ELABORA IMMEDIATAMENTE IL FILE con nome corretto
        await self._process_inventory_immediately(update, context, business_name)
    
    async def _handle_inventory_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce l'upload della foto inventario"""
        telegram_id = update.effective_user.id
        photo = update.message.photo[-1]  # Prendi la foto più grande
        business_name = context.user_data.get('onboarding_data', {}).get('business_name', 'Temporaneo')
        
        # Ringrazia per la foto
        await update.message.reply_text(
            f"✅ **Perfetto! Foto inventario ricevuta!**\n\n"
            f"📷 Sto elaborando l'immagine di **{business_name}** con OCR per estrarre i dati dell'inventario...\n\n"
            f"🔄 **Elaborazione in corso...**"
        )
        
        # Salva la foto per l'elaborazione
        context.user_data['inventory_photo'] = {
            'file_id': photo.file_id,
            'file_size': photo.file_size
        }
        
        logger.info(f"Foto inventario ricevuta da {telegram_id}")
        
        # ELABORA IMMEDIATAMENTE LA FOTO con nome corretto
        await self._process_inventory_immediately(update, context, business_name)
    
    async def _process_inventory_immediately(self, update: Update, context: ContextTypes.DEFAULT_TYPE, business_name: str) -> None:
        """Elabora immediatamente il file inventario"""
        from .processor_client import processor_client
        
        telegram_id = update.effective_user.id
        
        try:
            # Prepara i dati per l'elaborazione
            if 'inventory_file' in context.user_data:
                file_data = context.user_data['inventory_file']
                file_type = 'csv' if file_data['file_name'].endswith('.csv') else 'excel'
                
                # Scarica il file dal Telegram
                file_obj = await context.bot.get_file(file_data['file_id'])
                file_content = await file_obj.download_as_bytearray()
                file_name = file_data['file_name']
                
            elif 'inventory_photo' in context.user_data:
                photo_data = context.user_data['inventory_photo']
                file_type = 'photo'
                
                # Scarica la foto dal Telegram
                file_obj = await context.bot.get_file(photo_data['file_id'])
                file_content = await file_obj.download_as_bytearray()
                file_name = 'inventario.jpg'
                
            else:
                logger.error("Nessun file inventario trovato per elaborazione immediata")
                return
            
            # Invia al microservizio processor
            logger.info(f"📤 Invio dati al processor: telegram_id={telegram_id}, business_name={business_name}, file_type={file_type}")
            
            result = await processor_client.process_inventory(
                telegram_id=telegram_id,
                business_name=business_name,  # Nome corretto del locale
                file_type=file_type,
                file_content=file_content,
                file_name=file_name,
                file_id=file_data.get('file_id') if 'inventory_file' in context.user_data else photo_data.get('file_id')
            )
            
            if result.get('status') == 'success':
                saved_wines = result.get('saved_wines', result.get('total_wines', 0))
                warnings_count = result.get('warnings_count', 0)
                
                logger.info(f"✅ Inventario elaborato: {saved_wines} vini salvati")
                if warnings_count > 0:
                    logger.warning(f"⚠️ {warnings_count} vini salvati con warning/errori")
                
                # Salva il risultato per il completamento
                context.user_data['processed_wines'] = saved_wines
                context.user_data['warnings_count'] = warnings_count
                context.user_data['inventory_processed'] = True
                
                # Completa l'onboarding
                await self._complete_onboarding_final(update, context, business_name)
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                logger.error(f"❌ Errore processor: {error_msg}")
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {error_msg[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
                        
        except Exception as e:
            logger.error(f"Errore elaborazione inventario: {e}")
            await update.message.reply_text(
                "⚠️ Errore durante l'elaborazione. Riprova più tardi."
            )
    
    async def _complete_onboarding_final(self, update: Update, context: ContextTypes.DEFAULT_TYPE, business_name: str) -> None:
        """Completa l'onboarding dopo l'elaborazione del file"""
        telegram_id = update.effective_user.id
        
        try:
            # Aggiorna utente con nome locale e completa onboarding
            db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                business_name=business_name,
                onboarding_completed=True
            )
            
            # Messaggio di completamento
            processed_wines = context.user_data.get('processed_wines', 0)
            warnings_count = context.user_data.get('warnings_count', 0)
            
            message = (
                f"🎉 **Onboarding completato con successo!**\n\n"
                f"🏢 **{business_name}** è ora configurato!\n\n"
                f"✅ **{processed_wines} vini** elaborati e salvati\n"
            )
            
            if warnings_count > 0:
                message += (
                    f"⚠️ **{warnings_count} vini** salvati con warning/errori\n"
                    f"📝 I dettagli sono nelle note di ogni vino\n\n"
                )
            
            message += (
                f"✅ Inventario giorno 0 salvato\n"
                f"✅ Sistema pronto per l'uso\n\n"
                f"💬 Ora puoi comunicare i movimenti inventario in modo naturale!\n"
                f"📋 Usa /help per vedere tutti i comandi disponibili."
            )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
            # Pulisci dati temporanei
            context.user_data.pop('onboarding_step', None)
            context.user_data.pop('onboarding_data', None)
            context.user_data.pop('inventory_file', None)
            context.user_data.pop('inventory_photo', None)
            context.user_data.pop('processed_wines', None)
            context.user_data.pop('inventory_processed', None)
            
            logger.info(f"Onboarding completato per {business_name} (ID: {telegram_id})")
            
        except Exception as e:
            logger.error(f"Errore completamento onboarding: {e}")
            await update.message.reply_text(
                "❌ Errore durante il completamento. Riprova con `/start`."
            )
    
    async def _handle_text_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce la risposta testuale (nome locale)"""
        from .ai import get_ai_response
        
        telegram_id = update.effective_user.id
        business_name = update.message.text.strip()
        
        if context.user_data.get('onboarding_step') == 'waiting_business_name':
            # Salva nome locale e completa onboarding
            await self._complete_onboarding(update, context, business_name)
        else:
            # Usa AI per rispondere a domande generiche
            ai_prompt = f"""
            Sei Gio.ia-bot durante l'onboarding. L'utente ha scritto: "{business_name}"
            
            GUIDA L'ONBOARDING:
            - Se l'utente fornisce il nome del locale, conferma e procedi
            - Se l'utente fa domande, rispondi e guida al prossimo step
            - Sii sempre gentile e professionale
            - Mantieni il focus sull'onboarding
            
            STATO: Aspettando nome del locale
            """
            
            ai_response = get_ai_response(ai_prompt, telegram_id)
            await update.message.reply_text(ai_response)
    
    async def _complete_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE, business_name: str) -> None:
        """Completa l'onboarding e salva tutto nel database"""
        telegram_id = update.effective_user.id
        
        try:
            # Aggiorna utente con nome locale
            db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                business_name=business_name,
                onboarding_completed=True
            )
            
            # Elabora inventario e crea backup
            await self._process_inventory_and_backup(update, context, business_name)
            
            # Messaggio di completamento
            await update.message.reply_text(
                f"🎉 **Onboarding completato con successo!**\n\n"
                f"🏢 **{business_name}** è ora configurato!\n\n"
                f"✅ Inventario giorno 0 salvato\n"
                f"✅ Sistema pronto per l'uso\n\n"
                f"💬 Ora puoi comunicare i movimenti inventario in modo naturale!\n"
                f"📋 Usa /help per vedere tutti i comandi disponibili."
            )
            
            # Pulisci dati temporanei
            context.user_data.pop('onboarding_step', None)
            context.user_data.pop('onboarding_data', None)
            context.user_data.pop('inventory_file', None)
            context.user_data.pop('inventory_photo', None)
            
            logger.info(f"Onboarding completato per {business_name} (ID: {telegram_id})")
            
        except Exception as e:
            logger.error(f"Errore completamento onboarding: {e}")
            await update.message.reply_text(
                "❌ Errore durante il completamento. Riprova con `/start`."
            )
    
    async def _process_inventory_and_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE, business_name: str) -> None:
        """Elabora l'inventario e crea il backup del giorno 0"""
        from .processor_client import processor_client
        
        telegram_id = update.effective_user.id
        
        try:
            # Prepara i dati per l'elaborazione
            if 'inventory_file' in context.user_data:
                file_data = context.user_data['inventory_file']
                file_type = 'csv' if file_data['file_name'].endswith('.csv') else 'excel'
                
                # Scarica il file dal Telegram
                file_obj = await context.bot.get_file(file_data['file_id'])
                file_content = await file_obj.download_as_bytearray()
                file_name = file_data['file_name']
                
            elif 'inventory_photo' in context.user_data:
                photo_data = context.user_data['inventory_photo']
                file_type = 'photo'
                
                # Scarica la foto dal Telegram
                file_obj = await context.bot.get_file(photo_data['file_id'])
                file_content = await file_obj.download_as_bytearray()
                file_name = 'inventario.jpg'
                
            else:
                logger.error("Nessun file inventario trovato")
                return
            
            # Invia al microservizio processor
            logger.info(f"📤 Invio dati al processor: telegram_id={telegram_id}, business_name={business_name}, file_type={file_type}")
            
            result = await processor_client.process_inventory(
                telegram_id=telegram_id,
                business_name=business_name,
                file_type=file_type,
                file_content=file_content,
                file_name=file_name
            )
            
            if result.get('status') == 'success':
                logger.info(f"✅ Inventario elaborato: {result.get('total_wines', 0)} vini")
                
                # Notifica completamento all'utente
                await update.message.reply_text(
                    f"🎉 **Elaborazione completata!**\n\n"
                    f"✅ **{result.get('total_wines', 0)} vini** elaborati e salvati\n"
                    f"🏢 **{business_name}** configurato con successo\n\n"
                    f"💬 Ora puoi comunicare i movimenti inventario in modo naturale!"
                )
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                logger.error(f"❌ Errore processor: {error_msg}")
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {error_msg[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
                        
        except Exception as e:
            logger.error(f"Errore elaborazione inventario: {e}")
            await update.message.reply_text(
                "⚠️ Errore durante l'elaborazione. Riprova più tardi."
            )
    
    def is_onboarding_complete(self, telegram_id: int) -> bool:
        """Verifica se l'onboarding è completato"""
        user = db_manager.get_user_by_telegram_id(telegram_id)
        return user and user.onboarding_completed if user else False

# Istanza globale del nuovo gestore onboarding
new_onboarding_manager = NewOnboardingManager()
