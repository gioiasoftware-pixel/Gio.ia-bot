"""
Processore OCR per foto inventario
Estrae dati vini da immagini usando pytesseract
"""
import io
import logging
import re
from typing import List, Dict, Any
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)

class OCRProcessor:
    """Processore OCR per foto inventario"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def process_photo(self, file_content: bytes, file_name: str) -> List[Dict[str, Any]]:
        """
        Elabora una foto inventario con OCR
        
        Args:
            file_content: Contenuto binario della foto
            file_name: Nome del file
            
        Returns:
            Lista di vini estratti
        """
        try:
            self.logger.info(f"Elaborazione OCR foto: {file_name}")
            
            # Carica immagine
            image = Image.open(io.BytesIO(file_content))
            
            # Estrai testo con OCR
            text = pytesseract.image_to_string(image, lang='ita+eng')
            self.logger.info(f"Testo estratto: {len(text)} caratteri")
            
            # Pulisci e analizza il testo
            wines = self._parse_ocr_text(text)
            
            self.logger.info(f"Vini estratti da OCR: {len(wines)}")
            return wines
            
        except Exception as e:
            self.logger.error(f"Errore OCR: {e}")
            return []
    
    def _parse_ocr_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Analizza il testo estratto dall'OCR per trovare vini
        
        Args:
            text: Testo estratto dall'OCR
            
        Returns:
            Lista di vini estratti
        """
        wines = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Cerca pattern comuni di vini
            wine_data = self._extract_wine_from_line(line)
            if wine_data:
                wines.append(wine_data)
        
        return wines
    
    def _extract_wine_from_line(self, line: str) -> Dict[str, Any]:
        """
        Estrae dati vino da una singola riga
        
        Args:
            line: Riga di testo
            
        Returns:
            Dati vino o None
        """
        try:
            # Pulisci la riga
            line = re.sub(r'\s+', ' ', line).strip()
            
            # Pattern comuni per vini
            patterns = [
                # "Nome Vino - Produttore - Quantità"
                r'^([^-]+?)\s*-\s*([^-]+?)\s*-\s*(\d+)$',
                # "Nome Vino (Produttore) - Quantità"
                r'^([^(]+?)\s*\(([^)]+)\)\s*-\s*(\d+)$',
                # "Nome Vino, Produttore, Quantità"
                r'^([^,]+?),\s*([^,]+?),\s*(\d+)$',
            ]
            
            for pattern in patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    producer = match.group(2).strip()
                    quantity = int(match.group(3))
                    
                    # Filtra righe troppo corte o generiche
                    if len(name) < 3 or len(producer) < 2:
                        continue
                    
                    return {
                        'name': name,
                        'producer': producer,
                        'quantity': quantity,
                        'min_quantity': max(1, quantity // 4),  # 25% della quantità
                        'wine_type': self._detect_wine_type(name),
                        'notes': f"Estratto da OCR: {line[:50]}..."
                    }
            
            # Se non trova pattern specifici, prova a estrarre nome e quantità
            return self._extract_simple_wine(line)
            
        except Exception as e:
            self.logger.error(f"Errore estrazione vino da riga '{line}': {e}")
            return None
    
    def _extract_simple_wine(self, line: str) -> Dict[str, Any]:
        """
        Estrae vino con pattern più semplici
        
        Args:
            line: Riga di testo
            
        Returns:
            Dati vino o None
        """
        # Cerca numeri nella riga (possibile quantità)
        numbers = re.findall(r'\d+', line)
        if not numbers:
            return None
        
        # Prendi il primo numero come quantità
        quantity = int(numbers[0])
        
        # Rimuovi numeri e caratteri speciali per ottenere il nome
        name = re.sub(r'\d+', '', line)
        name = re.sub(r'[^\w\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        
        if len(name) < 3:
            return None
        
        return {
            'name': name,
            'producer': 'Sconosciuto',
            'quantity': quantity,
            'min_quantity': max(1, quantity // 4),
            'wine_type': self._detect_wine_type(name),
            'notes': f"Estratto da OCR: {line[:50]}..."
        }
    
    def _detect_wine_type(self, name: str) -> str:
        """
        Rileva il tipo di vino dal nome
        
        Args:
            name: Nome del vino
            
        Returns:
            Tipo di vino
        """
        name_lower = name.lower()
        
        if any(word in name_lower for word in ['champagne', 'spumante', 'prosecco', 'franciacorta']):
            return 'spumante'
        elif any(word in name_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio']):
            return 'bianco'
        elif any(word in name_lower for word in ['rosato', 'rose', 'rosé']):
            return 'rosato'
        else:
            return 'rosso'  # Default
