"""
Gestione upload file inventario - VERSIONE SEMPLIFICATA
NOTA: L'elaborazione dei file è ora gestita dal microservizio processor
"""
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database_async import Wine  # Solo per modello se necessario

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
    
    def estimate_processing_time(self, file_type: str, file_size: int, file_content: Optional[bytes] = None) -> Tuple[int, int]:
        """
        Stima tempo elaborazione inventario in secondi.
        
        Args:
            file_type: 'csv', 'excel', 'photo', 'pdf'
            file_size: Dimensione file in bytes
            file_content: Contenuto file opzionale per stima più precisa
            
        Returns:
            (tempo_min_secondi, tempo_max_secondi)
        """
        # Stima numero vini approssimativo basato su dimensione file
        estimated_wines = 0
        
        if file_type in ['csv', 'excel']:
            # CSV/Excel: ~200-500 bytes per riga (dipende da numero colonne)
            # Stimiamo 300 bytes per riga in media
            avg_bytes_per_row = 300
            estimated_wines = max(1, int(file_size / avg_bytes_per_row))
            
            # Overhead: parsing, mapping colonne, AI se necessario (5-15 sec)
            overhead_min = 5
            overhead_max = 15
            
            # Tempo per vino: validazione, normalizzazione, DB (0.3-1.0 sec)
            per_wine_min = 0.3
            per_wine_max = 1.0
            
        elif file_type == 'photo':
            # OCR: molto più variabile, difficile da stimare
            # Basato su risoluzione/qualità immagine, stimiamo 10-50 vini per immagine tipica
            # Per immagini più grandi, più vini potenzialmente visibili
            if file_size < 100_000:  # < 100KB
                estimated_wines = 10
            elif file_size < 500_000:  # < 500KB
                estimated_wines = 25
            elif file_size < 1_000_000:  # < 1MB
                estimated_wines = 40
            else:  # >= 1MB
                estimated_wines = 60
            
            # Overhead: preprocessing, OCR, estrazione (15-45 sec)
            overhead_min = 15
            overhead_max = 45
            
            # Tempo per vino: parsing OCR, AI enhancement (2-5 sec)
            per_wine_min = 2
            per_wine_max = 5
            
        elif file_type == 'pdf':
            # PDF: simile a CSV se pulito, altrimenti simile a OCR
            # Stimiamo basandoci su dimensione
            avg_bytes_per_wine = 400  # PDF tende ad essere più verboso
            estimated_wines = max(1, int(file_size / avg_bytes_per_wine))
            
            # Overhead: estrazione testo PDF (10-30 sec)
            overhead_min = 10
            overhead_max = 30
            
            # Tempo per vino: 1-3 sec (intermedio tra CSV e OCR)
            per_wine_min = 1
            per_wine_max = 3
            
        else:
            # Tipo sconosciuto: stima conservativa
            estimated_wines = 20
            overhead_min = 10
            overhead_max = 30
            per_wine_min = 1
            per_wine_max = 3
        
        # Calcola tempo totale
        time_min = int(overhead_min + (estimated_wines * per_wine_min))
        time_max = int(overhead_max + (estimated_wines * per_wine_max))
        
        # Arrotonda a multipli di 5 secondi per leggibilità
        time_min = ((time_min + 4) // 5) * 5
        time_max = ((time_max + 4) // 5) * 5
        
        # Limita range minimo
        time_min = max(10, time_min)  # Almeno 10 secondi
        time_max = max(time_min + 5, time_max)  # Max almeno 5 sec più di min
        
        return time_min, time_max
    
    def format_estimated_time(self, time_min: int, time_max: int) -> str:
        """
        Formatta tempo stimato in formato leggibile (es. "1-3 minuti", "30-60 secondi").
        """
        def format_seconds(sec: int) -> str:
            if sec < 60:
                return f"{sec} secondi"
            elif sec < 3600:
                minutes = sec // 60
                return f"{minutes} {'minuto' if minutes == 1 else 'minuti'}"
            else:
                hours = sec // 3600
                minutes = (sec % 3600) // 60
                if minutes == 0:
                    return f"{hours} {'ora' if hours == 1 else 'ore'}"
                else:
                    return f"{hours} {'ora' if hours == 1 else 'ore'} e {minutes} {'minuto' if minutes == 1 else 'minuti'}"
        
        time_min_str = format_seconds(time_min)
        time_max_str = format_seconds(time_max)
        
        if time_min == time_max:
            return time_min_str
        
        # Se stesso formato (entrambi secondi o entrambi minuti), semplifica
        if time_min < 60 and time_max < 60:
            return f"{time_min}-{time_max} secondi"
        elif time_min >= 60 and time_max < 3600 and (time_min // 60) == (time_max // 60):
            minutes = time_min // 60
            return f"{minutes} {'minuto' if minutes == 1 else 'minuti'}"
        else:
            return f"{time_min_str} - {time_max_str}"

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce upload documenti (CSV, Excel)"""
        from .processor_client import processor_client
        from .database_async import async_db_manager
        from .locks import user_mutex
        from .structured_logging import log_with_context, get_request_context
        import uuid
        
        try:
            document = update.message.document
            file_name = document.file_name.lower()
            telegram_id = update.effective_user.id
            update_id = update.update_id
            message_id = update.message.message_id
            correlation_id = get_request_context().get("correlation_id") or str(uuid.uuid4())
            client_msg_id = f"telegram:{update_id}:{message_id}"
            
            log_with_context(
                "info",
                f"File upload started: {document.file_name}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            # Verifica tipo file supportato
            if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
                await update.message.reply_text(
                    "❌ **Formato file non supportato**\n\n"
                    "Formati supportati:\n"
                    "• CSV (.csv)\n"
                    "• Excel (.xlsx, .xls)\n\n"
                    "Riprova con un file valido.",
                    parse_mode='Markdown'
                )
                return False
            
            # ✅ LOCK per serializzare upload stesso utente
            try:
                async with user_mutex(telegram_id, timeout_seconds=300, block_timeout=10):
                    # Scarica il file
                    file_obj = await context.bot.get_file(document.file_id)
                    file_content = await file_obj.download_as_bytearray()
                    
                    # Determina tipo file
                    file_type = 'csv' if file_name.endswith('.csv') else 'excel'
                    
                    # Stima tempo elaborazione
                    time_min, time_max = self.estimate_processing_time(file_type, document.file_size, file_content)
                    time_estimate = self.format_estimated_time(time_min, time_max)
                    
                    # Escapa caratteri speciali nel nome file per Markdown
                    safe_file_name = document.file_name.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
                    
                    await update.message.reply_text(
                        "✅ **File ricevuto!**\n\n"
                        f"📄 **Nome**: {safe_file_name}\n"
                        f"📊 **Dimensione**: {document.file_size:,} bytes\n\n"
                        "🔄 **Elaborazione in corso...**\n"
                        f"⏱️ **Tempo stimato**: {time_estimate}\n\n"
                        "Il file verrà processato dal sistema di elaborazione.",
                        parse_mode='Markdown'
                    )
                    
                    # ✅ Recupera business_name dal database utente - ASYNC
                    user = await async_db_manager.get_user_by_telegram_id(telegram_id)
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
                                "Altrimenti i dati verranno salvati temporaneamente con nome 'Upload Manuale'.",
                                parse_mode='Markdown'
                            )
                    
                    # ✅ Invia file e ottieni job_id con client_msg_id e correlation_id
                    job_response = await processor_client.process_inventory(
                        telegram_id=telegram_id,
                        business_name=business_name,
                        file_type=file_type,
                        file_content=file_content,
                        file_name=document.file_name,
                        client_msg_id=client_msg_id,  # Per idempotenza
                        correlation_id=correlation_id  # Per logging
                    )
            except RuntimeError as e:
                # Lock non ottenuto - utente sta già caricando un file
                await update.message.reply_text(
                    "⏳ **Operazione in corso**\n\n"
                    "Stai già caricando un file. Attendi il completamento prima di caricarne un altro.",
                    parse_mode='Markdown'
                )
                return False
            
            if job_response.get('status') == 'error':
                # Errore creando job
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {job_response.get('error', 'Errore sconosciuto')[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto.",
                    parse_mode='Markdown'
                )
                return True
            
            job_id = job_response.get('job_id')
            if not job_id:
                await update.message.reply_text(
                    f"⚠️ **Errore**: Nessun job_id ricevuto dal processor.",
                    parse_mode='Markdown'
                )
                return True
            
            # Stima tempo elaborazione per messaggio progress
            file_type = 'csv' if file_name.endswith('.csv') else 'excel'
            time_min, time_max = self.estimate_processing_time(file_type, len(file_content), file_content)
            time_estimate = self.format_estimated_time(time_min, time_max)
            
            # Escapa caratteri speciali nel nome file per Markdown
            safe_file_name = document.file_name.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
            
            # Notifica utente che elaborazione è iniziata
            progress_msg = await update.message.reply_text(
                f"✅ **File ricevuto!**\n\n"
                f"📄 **Nome**: {safe_file_name}\n"
                f"📊 **Dimensione**: {len(file_content):,} bytes\n"
                f"🔄 **Elaborazione in corso...**\n"
                f"⏱️ **Tempo stimato**: {time_estimate}\n"
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
            
            # Il processor restituisce: {status: 'completed', result: {status: 'success', ...}}
            # Estrai dati dal campo 'result' annidato se presente
            result_status = result.get('status')
            saved_wines = 0
            total_wines = 0
            warning_count = 0
            error_count = 0
            
            if result_status == 'completed':
                result_data = result.get('result', {})
                if result_data.get('status') == 'success':
                    # Job completato con successo - estrai dati da result_data
                    saved_wines = result_data.get('saved_wines', result_data.get('total_wines', 0))
                    total_wines = result_data.get('total_wines', 0)
                    warning_count = result_data.get('warning_count', 0)
                    error_count = result_data.get('error_count', 0)
                    logger.info(f"✅ Job {job_id} completato con successo: {saved_wines} vini salvati, {error_count} errori")
                else:
                    # Job completato ma con errore nel result
                    error_msg = result_data.get('error', 'Errore sconosciuto')
                    logger.error(f"Job completion error for {job_id}: {error_msg}, full result: {result}")
                    await update.message.reply_text(
                        f"⚠️ **Errore elaborazione inventario**\n\n"
                        f"Dettagli: {error_msg[:200]}\n\n"
                        f"📋 **Job ID:** `{job_id}`\n\n"
                        f"Riprova più tardi o contatta il supporto.",
                        parse_mode='Markdown'
                    )
                    return True
            elif result_status == 'success':
                # Compatibilità con formato vecchio - dati direttamente in result
                saved_wines = result.get('saved_wines', result.get('total_wines', 0))
                total_wines = result.get('total_wines', 0)
                warning_count = result.get('warning_count', 0)
                error_count = result.get('error_count', 0)
                logger.info(f"✅ Job {job_id} completato con successo (formato vecchio): {saved_wines} vini salvati")
            else:
                # Status diverso da completed o success
                error_msg = result.get('error', 'Errore sconosciuto')
                if not error_msg or error_msg == '...':
                    error_msg = f'Status job: {result_status}'
                
                logger.error(f"Job completion error for {job_id}: {error_msg}, full result: {result}")
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione inventario**\n\n"
                    f"Dettagli: {error_msg[:200]}\n\n"
                    f"📋 **Job ID:** `{job_id}`\n\n"
                    f"Riprova più tardi o contatta il supporto.",
                    parse_mode='Markdown'
                )
                return True
            
            # Se arriviamo qui, il job è completato con successo
            # I valori saved_wines, total_wines, etc. sono già stati estratti sopra
            if saved_wines > 0 or total_wines > 0:
                
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
                    f"• Consultare inventario: `/view`"
                )
                
                await update.message.reply_text(message, parse_mode='Markdown')
                
                # Se inventario caricato con successo e business_name valido, completa onboarding - ASYNC
                if error_count == 0 and business_name and business_name != "Upload Manuale":
                    await async_db_manager.update_user_onboarding(
                        telegram_id=telegram_id,
                        onboarding_completed=True
                    )
                    logger.info(f"Onboarding completato automaticamente dopo upload inventario per {telegram_id}/{business_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Errore gestione documento: {e}")
            await update.message.reply_text(
                "❌ **Errore durante l'upload**\n\n"
                "Si è verificato un errore durante la ricezione del file.\n"
                "Riprova con un file valido.",
                parse_mode='Markdown'
            )
            return False

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce upload foto per OCR"""
        from .processor_client import processor_client
        from .database_async import async_db_manager
        from .locks import user_mutex
        from .structured_logging import log_with_context, get_request_context
        import uuid
        
        try:
            # Prendi la foto con risoluzione più alta
            photo = update.message.photo[-1]
            telegram_id = update.effective_user.id
            update_id = update.update_id
            message_id = update.message.message_id
            correlation_id = get_request_context().get("correlation_id") or str(uuid.uuid4())
            client_msg_id = f"telegram:{update_id}:{message_id}"
            
            log_with_context(
                "info",
                f"Photo upload started: {photo.file_id}",
                telegram_id=telegram_id,
                correlation_id=correlation_id
            )
            
            # ✅ LOCK per serializzare upload stesso utente
            try:
                async with user_mutex(telegram_id, timeout_seconds=300, block_timeout=10):
                    # Scarica la foto
                    file_obj = await context.bot.get_file(photo.file_id)
                    file_content = await file_obj.download_as_bytearray()
                    
                    # Stima tempo elaborazione OCR
                    time_min, time_max = self.estimate_processing_time('photo', len(file_content), file_content)
                    time_estimate = self.format_estimated_time(time_min, time_max)
                    
                    await update.message.reply_text(
                        "✅ **Foto ricevuta!**\n\n"
                        f"📷 **Risoluzione**: {photo.width}x{photo.height}\n\n"
                        "🔄 **Elaborazione OCR in corso...**\n"
                        f"⏱️ **Tempo stimato**: {time_estimate}\n\n"
                        "La foto verrà processata per estrarre i dati dell'inventario.",
                        parse_mode='Markdown'
                    )
                    
                    # ✅ Recupera business_name dal database utente - ASYNC
                    user = await async_db_manager.get_user_by_telegram_id(telegram_id)
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
                                "Altrimenti i dati verranno salvati temporaneamente con nome 'Upload Manuale'.",
                                parse_mode='Markdown'
                            )
                    
                    # ✅ Invia file e ottieni job_id con client_msg_id e correlation_id
                    job_response = await processor_client.process_inventory(
                        telegram_id=telegram_id,
                        business_name=business_name,
                        file_type='photo',
                        file_content=file_content,
                        file_name='inventario.jpg',
                        client_msg_id=client_msg_id,  # Per idempotenza
                        correlation_id=correlation_id  # Per logging
                    )
            except RuntimeError as e:
                # Lock non ottenuto - utente sta già caricando un file
                await update.message.reply_text(
                    "⏳ **Operazione in corso**\n\n"
                    "Stai già caricando un file. Attendi il completamento prima di caricarne un altro.",
                    parse_mode='Markdown'
                )
                return False
            
            if job_response.get('status') == 'error':
                # Errore creando job
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione OCR**\n\n"
                    f"Dettagli: {job_response.get('error', 'Errore sconosciuto')[:200]}...\n\n"
                    f"Riprova più tardi o contatta il supporto.",
                    parse_mode='Markdown'
                )
                return True
            
            job_id = job_response.get('job_id')
            if not job_id:
                await update.message.reply_text(
                    f"⚠️ **Errore**: Nessun job_id ricevuto dal processor.",
                    parse_mode='Markdown'
                )
                return True
            
            # Stima tempo elaborazione OCR per messaggio progress
            time_min, time_max = self.estimate_processing_time('photo', len(file_content), file_content)
            time_estimate = self.format_estimated_time(time_min, time_max)
            
            # Notifica utente che elaborazione è iniziata
            progress_msg = await update.message.reply_text(
                f"✅ **Foto ricevuta!**\n\n"
                f"🔄 **Elaborazione OCR in corso...**\n"
                f"⏱️ **Tempo stimato**: {time_estimate}\n"
                f"📋 Job ID: `{job_id}`\n\n"
                f"⏳ Attendere, l'elaborazione può richiedere alcuni minuti...",
                parse_mode='Markdown'
            )
            
            # Attendi completamento job
            result = await processor_client.wait_for_job_completion(
                job_id=job_id,
                max_wait_seconds=3600,  # 1 ora massimo
                poll_interval=30  # Poll ogni 30 secondi
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
                    f"• Consultare inventario: `/view`"
                )
                
                await update.message.reply_text(message, parse_mode='Markdown')
                
                # Se inventario caricato con successo e business_name valido, completa onboarding - ASYNC
                if error_count == 0 and business_name and business_name != "Upload Manuale":
                    await async_db_manager.update_user_onboarding(
                        telegram_id=telegram_id,
                        onboarding_completed=True
                    )
                    logger.info(f"Onboarding completato automaticamente dopo upload OCR per {telegram_id}/{business_name}")
            else:
                error_msg = result.get('error', 'Errore sconosciuto')
                if not error_msg or error_msg == '...':
                    error_msg = 'Errore durante il polling dello stato del job. Verifica i log del processor.'
                
                logger.error(f"Job completion error for {job_id}: {error_msg}, full result: {result}")
                await update.message.reply_text(
                    f"⚠️ **Errore elaborazione OCR**\n\n"
                    f"Dettagli: {error_msg[:200]}\n\n"
                    f"💡 **Possibili cause:**\n"
                    f"• Processor non raggiungibile\n"
                    f"• Timeout durante l'elaborazione\n"
                    f"• Problema di connessione\n\n"
                    f"📋 **Job ID:** `{job_id}`\n\n"
                    f"Riprova più tardi o contatta il supporto.",
                    parse_mode='Markdown'
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Errore gestione foto: {e}")
            await update.message.reply_text(
                "❌ **Errore durante l'upload**\n\n"
                "Si è verificato un errore durante la ricezione della foto.\n"
                "Riprova con un'immagine più chiara.",
                parse_mode='Markdown'
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
    
    async def start_upload_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il processo di upload inventario"""
        instructions = self.get_upload_instructions()
        await update.message.reply_text(instructions, parse_mode='Markdown')
    
    async def show_csv_example(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await update.message.reply_text(example, parse_mode='Markdown')
    

# Istanza globale
file_upload_manager = FileUploadManager()
