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
            
            # Salva informazioni file per il processor
            context.user_data['inventory_file'] = {
                'file_id': document.file_id,
                'file_name': document.file_name,
                'file_size': document.file_size
            }
            
            await update.message.reply_text(
                "✅ **File ricevuto!**\n\n"
                f"📄 **Nome**: {document.file_name}\n"
                f"📊 **Dimensione**: {document.file_size:,} bytes\n\n"
                "🔄 **Elaborazione in corso...**\n"
                "Il file verrà processato dal sistema di elaborazione."
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
        try:
            # Prendi la foto con risoluzione più alta
            photo = update.message.photo[-1]
            
            # Salva informazioni foto per il processor
            context.user_data['inventory_photo'] = {
                'file_id': photo.file_id,
                'width': photo.width,
                'height': photo.height
            }
            
            await update.message.reply_text(
                "✅ **Foto ricevuta!**\n\n"
                f"📷 **Risoluzione**: {photo.width}x{photo.height}\n\n"
                "🔄 **Elaborazione OCR in corso...**\n"
                "La foto verrà processata per estrarre i dati dell'inventario."
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

# Istanza globale
file_upload_manager = FileUploadManager()
