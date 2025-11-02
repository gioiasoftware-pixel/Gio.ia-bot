"""
Gestione upload file inventario - VERSIONE SEMPLIFICATA
NOTA: L'elaborazione dei file è ora gestita dal microservizio processor
"""
import os
import logging
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database import db_manager, Wine

logger = logging.getLogger(__name__)

class FileUploadManager:
    """Gestore upload file inventario - VERSIONE SEMPLIFICATA"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.required_headers = [
            'Etichetta', 'Produttore', 'Uvaggio', 'Comune', 'Regione', 'Nazione',
            'Fornitore', 'Costo', 'Prezzo in carta', 'Quantità in magazzino',
            'Annata', 'Note', 'Denominazione', 'Formato', 'Alcol', 'Codice'
        ]

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce upload documenti (CSV, Excel)"""
        from .processor_client import processor_client
        
        try:
            document = update.message.document
            file_name = document.file_name.lower()
            
            # Verifica tipo file supportato
            if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
                await update.message.reply_text(
                    "❌ **Formato file non supportato**\n\n"
                    "Formati supportati:\n"
                    "• CSV (.csv)\n"
                    "• Excel (.xlsx, .xls)\n\n"
                    "Riprova con un file valido."
                )
                return False
            
            # Scarica il file
            file_obj = await context.bot.get_file(document.file_id)
            file_content = await file_obj.download_as_bytearray()
            
            # Determina tipo file
            file_type = 'csv' if file_name.endswith('.csv') else 'excel'
            
            await update.message.reply_text(
                "✅ **File ricevuto!**\n\n"
                f"📄 **Nome**: {document.file_name}\n"
                f"📊 **Dimensione**: {document.file_size:,} bytes\n\n"
                "🔄 **Elaborazione in corso...**\n"
                "Il file verrà processato dal sistema di elaborazione."
            )
            
            # Invia al processor
            telegram_id = update.effective_user.id
            
            # Recupera business_name dal database utente
            user = db_manager.get_user_by_telegram_id(telegram_id)
            if user and user.business_name and user.business_name != "Upload Manuale":
                business_name = user.business_name
            else:
                # Fallback se utente non ha ancora completato onboarding
                business_name = "Upload Manuale"
                logger.warning(f"User {telegram_id} non ha business_name valido, usando fallback")
                
                # Avvisa utente se non ha completato onboarding
                if not user or not user.onboarding_completed:
                    await update.message.reply_text(
                        "⚠️ **Attenzione:** Non hai ancora completato l'onboarding.\n\n"
                        "Per caricare il tuo inventario con il nome corretto del locale, completa prima l'onboarding con `/start`.\n\n"
                        "Altrimenti i dati verranno salvati temporaneamente con nome 'Upload Manuale'."
                    )
            
            # Invia file e ottieni job_id
            job_response = await processor_client.process_inventory(
                telegram_id=telegram_id,
                business_name=business_name,
                file_type=file_type,
                file_content=file_content,
                file_name=document.file_name
            )
            
            if job_response.get('status') == 'error':
                # Errore creando job
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {job_response.get('error', 'Errore sconosciuto')[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
                return True
            
            job_id = job_response.get('job_id')
            if not job_id:
                await update.message.reply_text(
                    f"⚠️ **Errore**: Nessun job_id ricevuto dal processor."
                )
                return True
            
            # Notifica utente che elaborazione è iniziata
            progress_msg = await update.message.reply_text(
                f"✅ **File ricevuto!**\n\n"
                f"📄 **Nome**: {document.file_name}\n"
                f"📊 **Dimensione**: {len(file_content):,} bytes\n"
                f"🔄 **Elaborazione in corso...**\n"
                f"📋 Job ID: `{job_id}`\n\n"
                f"⏳ Attendere, l'elaborazione può richiedere alcuni minuti...",
                parse_mode='Markdown'
            )
            
            # Attendi completamento job
            result = await processor_client.wait_for_job_completion(
                job_id=job_id,
                max_wait_seconds=3600,  # 1 ora massimo
                poll_interval=10  # Poll ogni 10 secondi
            )
            
            # Elimina messaggio progress
            try:
                await progress_msg.delete()
            except:
                pass
            
            if result.get('status') == 'success':
                saved_wines = result.get('saved_wines', result.get('total_wines', 0))
                total_wines = result.get('total_wines', 0)
                warning_count = result.get('warning_count', 0)  # Separato: solo warnings
                error_count = result.get('error_count', 0)      # Solo errori critici
                
                # Messaggio base
                if error_count > 0:
                    # Se ci sono errori critici, mostra messaggio di errore
                    message = (
                        f"⚠️ **Elaborazione completata con errori**\n\n"
                        f"✅ **{saved_wines} vini** salvati su {total_wines} elaborati\n"
                        f"❌ **{error_count} errori critici** durante l'elaborazione\n"
                    )
                    if warning_count > 0:
                        message += f"ℹ️ **{warning_count} warnings** (annate mancanti, dati opzionali)\n"
                    message += (
                        f"\n📝 Verifica i dettagli nelle note dei vini.\n"
                        f"💡 Riprova o contatta il supporto se il problema persiste.\n\n"
                    )
                else:
                    # Successo (con o senza warnings)
                    message = (
                        f"🎉 **Elaborazione completata!**\n\n"
                        f"✅ **{saved_wines} vini** salvati su {total_wines} elaborati\n"
                    )
                    
                    if warning_count > 0:
                        message += (
                            f"ℹ️ **{warning_count} warnings** (annate mancanti, dati opzionali)\n"
                            f"📝 I dettagli sono salvati nelle note di ogni vino\n"
                            f"💡 Verifica i vini nel tuo inventario per i dettagli\n\n"
                        )
                
                message += (
                    f"🏢 **{business_name}** aggiornato con successo\n\n"
                    f"🚀 **INVENTARIO OPERATIVO!**\n\n"
                    f"💬 **Ora puoi:**\n"
                    f"• Comunicare consumi: \"Ho venduto 3 Barolo\"\n"
                    f"• Comunicare rifornimenti: \"Ho ricevuto 10 Vermentino\"\n"
                    f"• Chiedere informazioni: \"Quanto Sassicaia ho in cantina?\"\n"
                    f"• Consultare inventario: `/inventario`"
                )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {error_msg[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Errore gestione documento: {e}")
            await update.message.reply_text(
                "❌ **Errore durante l'upload**\n\n"
                "Si è verificato un errore durante la ricezione del file.\n"
                "Riprova con un file valido."
            )
            return False

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce upload foto per OCR"""
        from .processor_client import processor_client
        
        try:
            # Prendi la foto con risoluzione più alta
            photo = update.message.photo[-1]
            
            # Scarica la foto
            file_obj = await context.bot.get_file(photo.file_id)
            file_content = await file_obj.download_as_bytearray()
            
            await update.message.reply_text(
                "✅ **Foto ricevuta!**\n\n"
                f"📷 **Risoluzione**: {photo.width}x{photo.height}\n\n"
                "🔄 **Elaborazione OCR in corso...**\n"
                "La foto verrà processata per estrarre i dati dell'inventario."
            )
            
            # Invia al processor
            telegram_id = update.effective_user.id
            
            # Recupera business_name dal database utente
            user = db_manager.get_user_by_telegram_id(telegram_id)
            if user and user.business_name and user.business_name != "Upload Manuale":
                business_name = user.business_name
            else:
                # Fallback se utente non ha ancora completato onboarding
                business_name = "Upload Manuale"
                logger.warning(f"User {telegram_id} non ha business_name valido, usando fallback")
                
                # Avvisa utente se non ha completato onboarding
                if not user or not user.onboarding_completed:
                    await update.message.reply_text(
                        "⚠️ **Attenzione:** Non hai ancora completato l'onboarding.\n\n"
                        "Per caricare il tuo inventario con il nome corretto del locale, completa prima l'onboarding con `/start`.\n\n"
                        "Altrimenti i dati verranno salvati temporaneamente con nome 'Upload Manuale'."
                    )
            
            # Invia file e ottieni job_id
            job_response = await processor_client.process_inventory(
                telegram_id=telegram_id,
                business_name=business_name,
                file_type='photo',
                file_content=file_content,
                file_name='inventario.jpg'
            )
            
            if job_response.get('status') == 'error':
                # Errore creando job
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione OCR**\n\n"
                    f"Dettagli: {job_response.get('error', 'Errore sconosciuto')[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
                return True
            
            job_id = job_response.get('job_id')
            if not job_id:
                await update.message.reply_text(
                    f"⚠️ **Errore**: Nessun job_id ricevuto dal processor."
                )
                return True
            
            # Notifica utente che elaborazione è iniziata
            progress_msg = await update.message.reply_text(
                f"✅ **Foto ricevuta!**\n\n"
                f"🔄 **Elaborazione OCR in corso...**\n"
                f"📋 Job ID: `{job_id}`\n\n"
                f"⏳ Attendere, l'elaborazione può richiedere alcuni minuti...",
                parse_mode='Markdown'
            )
            
            # Attendi completamento job
            result = await processor_client.wait_for_job_completion(
                job_id=job_id,
                max_wait_seconds=3600,  # 1 ora massimo
                poll_interval=10  # Poll ogni 10 secondi
            )
            
            # Elimina messaggio progress
            try:
                await progress_msg.delete()
            except:
                pass
            
            if result.get('status') == 'success':
                saved_wines = result.get('saved_wines', result.get('total_wines', 0))
                total_wines = result.get('total_wines', 0)
                warning_count = result.get('warning_count', 0)  # Separato: solo warnings
                error_count = result.get('error_count', 0)      # Solo errori critici
                
                # Messaggio base
                if error_count > 0:
                    # Se ci sono errori critici, mostra messaggio di errore
                    message = (
                        f"⚠️ **Elaborazione OCR completata con errori**\n\n"
                        f"✅ **{saved_wines} vini** estratti e salvati su {total_wines}\n"
                        f"❌ **{error_count} errori critici** durante l'elaborazione\n"
                    )
                    if warning_count > 0:
                        message += f"ℹ️ **{warning_count} warnings** (annate mancanti, dati opzionali)\n"
                    message += (
                        f"\n📝 Verifica i dettagli nelle note dei vini.\n"
                        f"💡 Riprova o contatta il supporto se il problema persiste.\n\n"
                    )
                else:
                    # Successo (con o senza warnings)
                    message = (
                        f"🎉 **Elaborazione OCR completata!**\n\n"
                        f"✅ **{saved_wines} vini** estratti e salvati su {total_wines}\n"
                    )
                    
                    if warning_count > 0:
                        message += (
                            f"ℹ️ **{warning_count} warnings** (annate mancanti, dati opzionali)\n"
                            f"📝 I dettagli sono salvati nelle note di ogni vino\n\n"
                        )
                
                message += (
                    f"🏢 **{business_name}** aggiornato con successo\n\n"
                    f"🚀 **INVENTARIO OPERATIVO!**\n\n"
                    f"💬 **Ora puoi:**\n"
                    f"• Comunicare consumi: \"Ho venduto 3 Barolo\"\n"
                    f"• Comunicare rifornimenti: \"Ho ricevuto 10 Vermentino\"\n"
                    f"• Chiedere informazioni: \"Quanto Sassicaia ho in cantina?\"\n"
                    f"• Consultare inventario: `/inventario`"
                )
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione OCR**\n\n"
                    f"Dettagli: {error_msg[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto."
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Errore gestione foto: {e}")
            await update.message.reply_text(
                "❌ **Errore durante l'upload**\n\n"
                "Si è verificato un errore durante la ricezione della foto.\n"
                "Riprova con un'immagine più chiara."
            )
            return False

    def get_upload_instructions(self) -> str:
        """Restituisce istruzioni per upload file"""
        return (
            "📤 **Come caricare il tuo inventario**\n\n"
            "**📋 File CSV/Excel:**\n"
            "• Invia il file direttamente in chat\n"
            "• Formati supportati: .csv, .xlsx, .xls\n"
            "• Assicurati che il file abbia le intestazioni corrette\n\n"
            "**📷 Foto/Immagine:**\n"
            "• Scatta una foto chiara dell'inventario\n"
            "• Assicurati che il testo sia leggibile\n"
            "• Evita riflessi e ombre\n\n"
            "**💡 Suggerimenti:**\n"
            "• Per file CSV: usa virgola come separatore\n"
            "• Per foto: posiziona il documento su una superficie piana\n"
            "• Verifica che tutti i dati siano visibili"
        )
    
    def start_upload_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il processo di upload inventario"""
        instructions = self.get_upload_instructions()
        update.message.reply_text(instructions, parse_mode='Markdown')
    
    def show_csv_example(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra esempio di file CSV"""
        example = (
            "📋 **Esempio file CSV:**\n\n"
            "```csv\n"
            "Nome,Produttore,Annata,Regione,Prezzo,Quantità,Tipo\n"
            "Chianti Classico,Antinori,2020,Toscana,25.50,12,Rosso\n"
            "Prosecco,La Marca,2021,Veneto,15.00,24,Spumante\n"
            "Pinot Grigio,Santa Margherita,2021,Veneto,18.00,18,Bianco\n"
            "```\n\n"
            "💡 **Suggerimenti:**\n"
            "• Usa virgola come separatore\n"
            "• Includi intestazioni nella prima riga\n"
            "• Salva come .csv"
        )
        update.message.reply_text(example, parse_mode='Markdown')
    
    def _process_csv(self, file_data: bytes) -> list:
        """Processa file CSV (metodo per compatibilità onboarding)"""
        # Questo metodo è per compatibilità con l'onboarding
        # L'elaborazione reale è ora gestita dal processor
        return []
    
    def _process_excel(self, file_data: bytes) -> list:
        """Processa file Excel (metodo per compatibilità onboarding)"""
        # Questo metodo è per compatibilità con l'onboarding
        # L'elaborazione reale è ora gestita dal processor
        return []
    
    def _process_photo_ocr(self, file_data: bytes) -> list:
        """Processa foto OCR (metodo per compatibilità onboarding)"""
        # Questo metodo è per compatibilità con l'onboarding
        # L'elaborazione reale è ora gestita dal processor
        return []

# Istanza globale
file_upload_manager = FileUploadManager()
