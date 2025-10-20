"""
Gestione upload file inventario (CSV, Excel, foto con OCR)
"""
import os
import logging
import pandas as pd
import pytesseract
from PIL import Image
import io
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database import db_manager, Wine

logger = logging.getLogger(__name__)

class FileUploadManager:
    """Gestore upload file inventario"""
    
    def __init__(self):
        # Intestazione CSV richiesta
        self.required_headers = [
            'Etichetta', 'Produttore', 'Uvaggio', 'Comune', 'Regione', 'Nazione',
            'Fornitore', 'Costo', 'Prezzo in carta', 'Quantità in magazzino',
            'Annata', 'Note', 'Denominazione', 'Formato', 'Alcol', 'Codice'
        ]
        
        # Mappatura colonne CSV -> campi database
        self.csv_mapping = {
            'Etichetta': 'name',
            'Produttore': 'producer',
            'Uvaggio': 'grape_variety',
            'Comune': 'region',
            'Regione': 'region',
            'Nazione': 'country',
            'Costo': 'cost_price',
            'Prezzo in carta': 'selling_price',
            'Quantità in magazzino': 'quantity',
            'Annata': 'vintage',
            'Note': 'notes',
            'Denominazione': 'classification',
            'Formato': 'description',
            'Alcol': 'alcohol_content'
        }
    
    def start_upload_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il processo di upload"""
        message = (
            "📤 **Upload Inventario**\n\n"
            "Puoi caricare il tuo inventario in diversi modi:\n\n"
            "📊 **File supportati:**\n"
            "• CSV (.csv)\n"
            "• Excel (.xlsx, .xls)\n"
            "• Foto/Immagine (.jpg, .png) - con OCR\n\n"
            "📋 **Intestazione CSV richiesta:**\n"
            "Etichetta, Produttore, Uvaggio, Comune, Regione, Nazione, Fornitore, Costo, Prezzo in carta, Quantità in magazzino, Annata, Note, Denominazione, Formato, Alcol, Codice\n\n"
            "💡 **Come procedere:**\n"
            "1. Prepara il file con l'intestazione corretta\n"
            "2. Invia il file come allegato\n"
            "3. Il bot processerà automaticamente i dati\n\n"
            "📷 **Per le foto:**\n"
            "Invia una foto chiara dell'inventario e userò l'OCR per estrarre i dati."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Esempio CSV", callback_data="csv_example")],
            [InlineKeyboardButton("❌ Annulla", callback_data="cancel_upload")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce l'upload di documenti (CSV, Excel)"""
        document = update.message.document
        file_name = document.file_name.lower()
        
        # Verifica tipo file
        if not (file_name.endswith('.csv') or file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            update.message.reply_text(
                "❌ **Formato file non supportato**\n\n"
                "Formati supportati:\n"
                "• CSV (.csv)\n"
                "• Excel (.xlsx, .xls)\n\n"
                "Riprova con un file valido."
            )
            return
        
        # Scarica il file
        file = context.bot.get_file(document.file_id)
        file_content = file.download_as_bytearray()
        
        try:
            # Processa il file
            if file_name.endswith('.csv'):
                wines_data = self._process_csv(file_content)
            else:  # Excel
                wines_data = self._process_excel(file_content)
            
            if not wines_data:
                update.message.reply_text(
                    "❌ **Errore nel file**\n\n"
                    "Il file non contiene dati validi o l'intestazione non è corretta.\n"
                    "Verifica che l'intestazione contenga tutte le colonne richieste."
                )
                return
            
            # Salva i vini nel database
            user = update.effective_user
            telegram_id = user.id
            saved_count = self._save_wines_to_db(telegram_id, wines_data)
            
            success_message = (
                f"✅ **Upload completato con successo!**\n\n"
                f"📊 **Risultati:**\n"
                f"• Vini processati: {len(wines_data)}\n"
                f"• Vini salvati: {saved_count}\n"
                f"• Errori: {len(wines_data) - saved_count}\n\n"
                f"💡 Usa `/inventario` per vedere il tuo inventario aggiornato!"
            )
            
            update.message.reply_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Errore processamento file: {e}")
            update.message.reply_text(
                "❌ **Errore durante il processamento**\n\n"
                "Si è verificato un errore durante l'elaborazione del file.\n"
                "Verifica che il file sia valido e riprova."
            )
    
    def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Gestisce l'upload di foto con OCR"""
        # Prendi la foto con risoluzione più alta
        photo = update.message.photo[-1]
        
        update.message.reply_text("📷 **Processando foto con OCR...**\n\nQuesto potrebbe richiedere qualche minuto...")
        
        try:
            # Scarica la foto
            file = context.bot.get_file(photo.file_id)
            image_data = file.download_as_bytearray()
            
            # Processa con OCR
            wines_data = self._process_photo_ocr(image_data)
            
            if not wines_data:
                update.message.reply_text(
                    "❌ **Nessun dato estratto**\n\n"
                    "Non sono riuscito a estrarre dati dall'immagine.\n"
                    "Assicurati che:\n"
                    "• L'immagine sia chiara e leggibile\n"
                    "• Il testo sia ben visibile\n"
                    "• L'inventario sia in formato tabellare\n\n"
                    "Riprova con un'immagine più chiara."
                )
                return
            
            # Salva i vini nel database
            user = update.effective_user
            telegram_id = user.id
            saved_count = self._save_wines_to_db(telegram_id, wines_data)
            
            success_message = (
                f"✅ **OCR completato con successo!**\n\n"
                f"📊 **Risultati:**\n"
                f"• Vini estratti: {len(wines_data)}\n"
                f"• Vini salvati: {saved_count}\n"
                f"• Errori: {len(wines_data) - saved_count}\n\n"
                f"💡 Usa `/inventario` per vedere il tuo inventario aggiornato!"
            )
            
            update.message.reply_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Errore OCR: {e}")
            update.message.reply_text(
                "❌ **Errore durante l'OCR**\n\n"
                "Si è verificato un errore durante l'elaborazione dell'immagine.\n"
                "Riprova con un'immagine più chiara."
            )
    
    def _process_csv(self, file_content: bytes) -> List[Dict[str, Any]]:
        """Processa file CSV"""
        try:
            # Leggi CSV
            df = pd.read_csv(io.BytesIO(file_content))
            
            # Verifica intestazione
            missing_headers = [h for h in self.required_headers if h not in df.columns]
            if missing_headers:
                logger.warning(f"Intestazioni mancanti: {missing_headers}")
                # Prova a mappare colonne simili
                df = self._map_similar_columns(df)
            
            return self._dataframe_to_wines(df)
            
        except Exception as e:
            logger.error(f"Errore processamento CSV: {e}")
            return []
    
    def _process_excel(self, file_content: bytes) -> List[Dict[str, Any]]:
        """Processa file Excel"""
        try:
            # Leggi Excel
            df = pd.read_excel(io.BytesIO(file_content))
            
            # Verifica intestazione
            missing_headers = [h for h in self.required_headers if h not in df.columns]
            if missing_headers:
                logger.warning(f"Intestazioni mancanti: {missing_headers}")
                # Prova a mappare colonne simili
                df = self._map_similar_columns(df)
            
            return self._dataframe_to_wines(df)
            
        except Exception as e:
            logger.error(f"Errore processamento Excel: {e}")
            return []
    
    def _process_photo_ocr(self, image_data: bytes) -> List[Dict[str, Any]]:
        """Processa foto con OCR"""
        try:
            # Carica immagine
            image = Image.open(io.BytesIO(image_data))
            
            # Configura OCR per italiano
            custom_config = r'--oem 3 --psm 6 -l ita'
            text = pytesseract.image_to_string(image, config=custom_config)
            
            # Processa il testo estratto
            return self._parse_ocr_text(text)
            
        except Exception as e:
            logger.error(f"Errore OCR: {e}")
            return []
    
    def _parse_ocr_text(self, text: str) -> List[Dict[str, Any]]:
        """Parsa il testo estratto dall'OCR"""
        wines_data = []
        lines = text.split('\n')
        
        # Cerca intestazioni
        header_line = None
        for i, line in enumerate(lines):
            if any(header in line for header in ['Etichetta', 'Produttore', 'Nome']):
                header_line = i
                break
        
        if header_line is None:
            return []
        
        # Processa righe successive
        for line in lines[header_line + 1:]:
            if line.strip():
                # Dividi per tab o spazi multipli
                parts = [p.strip() for p in line.split('\t') if p.strip()]
                if len(parts) >= 3:  # Minimo: nome, produttore, quantità
                    wine_data = {
                        'name': parts[0] if len(parts) > 0 else '',
                        'producer': parts[1] if len(parts) > 1 else '',
                        'quantity': self._extract_number(parts[2]) if len(parts) > 2 else 0,
                        'vintage': self._extract_vintage(line),
                        'wine_type': self._detect_wine_type(line)
                    }
                    wines_data.append(wine_data)
        
        return wines_data
    
    def _extract_number(self, text: str) -> int:
        """Estrae numero da testo"""
        import re
        numbers = re.findall(r'\d+', text)
        return int(numbers[0]) if numbers else 0
    
    def _extract_vintage(self, text: str) -> Optional[int]:
        """Estrae annata da testo"""
        import re
        years = re.findall(r'\b(19|20)\d{2}\b', text)
        return int(years[0]) if years else None
    
    def _detect_wine_type(self, text: str) -> str:
        """Rileva tipo di vino da testo"""
        text_lower = text.lower()
        if any(word in text_lower for word in ['rosso', 'red', 'nero']):
            return 'Rosso'
        elif any(word in text_lower for word in ['bianco', 'white', 'blanc']):
            return 'Bianco'
        elif any(word in text_lower for word in ['rosato', 'rose', 'pink']):
            return 'Rosato'
        elif any(word in text_lower for word in ['spumante', 'champagne', 'prosecco']):
            return 'Spumante'
        return 'Rosso'  # Default
    
    def _map_similar_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mappa colonne simili alle intestazioni richieste"""
        column_mapping = {}
        
        for col in df.columns:
            col_lower = col.lower()
            for required in self.required_headers:
                required_lower = required.lower()
                if (required_lower in col_lower or 
                    col_lower in required_lower or
                    self._similarity(col_lower, required_lower) > 0.7):
                    column_mapping[col] = required
                    break
        
        return df.rename(columns=column_mapping)
    
    def _similarity(self, a: str, b: str) -> float:
        """Calcola similarità tra stringhe"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()
    
    def _dataframe_to_wines(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Converte DataFrame in lista di vini"""
        wines_data = []
        
        for _, row in df.iterrows():
            wine_data = {}
            
            for csv_col, db_field in self.csv_mapping.items():
                if csv_col in df.columns:
                    value = row[csv_col]
                    
                    # Gestisci valori NaN
                    if pd.isna(value):
                        value = None
                    
                    # Conversione tipi
                    if db_field == 'quantity' and value is not None:
                        try:
                            wine_data[db_field] = int(float(str(value)))
                        except (ValueError, TypeError):
                            wine_data[db_field] = 0
                    elif db_field in ['cost_price', 'selling_price', 'alcohol_content'] and value is not None:
                        try:
                            wine_data[db_field] = float(str(value))
                        except (ValueError, TypeError):
                            wine_data[db_field] = None
                    elif db_field == 'vintage' and value is not None:
                        try:
                            wine_data[db_field] = int(float(str(value)))
                        except (ValueError, TypeError):
                            wine_data[db_field] = None
                    else:
                        wine_data[db_field] = str(value) if value is not None else None
            
            # Valori di default
            wine_data.setdefault('quantity', 0)
            wine_data.setdefault('min_quantity', 0)
            
            wines_data.append(wine_data)
        
        return wines_data
    
    def _save_wines_to_db(self, telegram_id: int, wines_data: List[Dict[str, Any]]) -> int:
        """Salva vini nel database"""
        saved_count = 0
        
        for wine_data in wines_data:
            try:
                wine = db_manager.add_wine(telegram_id, wine_data)
                if wine:
                    saved_count += 1
            except Exception as e:
                logger.error(f"Errore salvataggio vino: {e}")
        
        return saved_count
    
    def show_csv_example(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Mostra esempio di CSV"""
        example_csv = (
            "📋 **Esempio CSV corretto:**\n\n"
            "```csv\n"
            "Etichetta,Produttore,Uvaggio,Comune,Regione,Nazione,Fornitore,Costo,Prezzo in carta,Quantità in magazzino,Annata,Note,Denominazione,Formato,Alcol,Codice\n"
            "Chianti Classico,Antinori,Sangiovese,Greve in Chianti,Toscana,Italia,Antinori,15.50,25.00,50,2020,Note speciali,DOCG,0.75L,13.5,ANT001\n"
            "Barolo,Gaja,Nebbiolo,Barolo,Piemonte,Italia,Gaja,45.00,75.00,25,2019,Annata eccezionale,DOCG,0.75L,14.0,GAJ002\n"
            "```\n\n"
            "💡 **Suggerimenti:**\n"
            "• Usa virgole come separatori\n"
            "• Mantieni l'intestazione esatta\n"
            "• I campi opzionali possono essere vuoti\n"
            "• I prezzi usano il punto come decimale"
        )
        
        update.callback_query.edit_message_text(example_csv, parse_mode='Markdown')

# Istanza globale del gestore upload
file_upload_manager = FileUploadManager()
