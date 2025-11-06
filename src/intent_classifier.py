"""
Intent Classifier - Classifica intento messaggio senza AI, con 5 retry
Riutilizza pattern da inventory_movements.py senza modificarli
"""
import re
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """Rappresenta un intento classificato"""
    type: str  # "movement_consumption", "movement_replenishment", "search", "inventory_list", "unknown"
    confidence: float  # 0.0 - 1.0
    parameters: Dict[str, Any]
    handler: Optional[str] = None  # Nome funzione da chiamare
    retry_count: int = 0  # Numero retry che ha trovato l'intent


class IntentClassifier:
    """Classifica intento messaggio senza AI, con 5 retry"""
    
    def __init__(self):
        # Importa pattern da inventory_movements (solo lettura, non modifica)
        from .inventory_movements import InventoryMovementManager, word_to_number
        self.movement_manager = InventoryMovementManager()
        self.word_to_number = word_to_number
    
    async def classify_with_retry(self, message: str, telegram_id: int) -> Intent:
        """Classifica con 5 retry"""
        message_lower = message.lower().strip()
        
        # Retry 1: Pattern movimenti standard (strict)
        intent = await self._classify_movements(message_lower, strict=True)
        if intent.type != "unknown":
            intent.retry_count = 1
            logger.info(f"[INTENT_CLASSIFIER] Intent trovato al retry 1: {intent.type} (confidence={intent.confidence:.2f})")
            return intent
        
        # Retry 2: Pattern permissivi (case-insensitive)
        intent = await self._classify_movements(message_lower, strict=False)
        if intent.type != "unknown":
            intent.retry_count = 2
            logger.info(f"[INTENT_CLASSIFIER] Intent trovato al retry 2: {intent.type} (confidence={intent.confidence:.2f})")
            return intent
        
        # Retry 3: Keyword matching
        intent = await self._classify_by_keywords(message_lower)
        if intent.type != "unknown":
            intent.retry_count = 3
            logger.info(f"[INTENT_CLASSIFIER] Intent trovato al retry 3: {intent.type} (confidence={intent.confidence:.2f})")
            return intent
        
        # Retry 4: Normalizzazione testo
        normalized = self._normalize_text(message_lower)
        if normalized != message_lower:
            intent = await self._classify_movements(normalized, strict=False)
            if intent.type != "unknown":
                intent.retry_count = 4
                logger.info(f"[INTENT_CLASSIFIER] Intent trovato al retry 4: {intent.type} (confidence={intent.confidence:.2f})")
                return intent
        
        # Retry 5: Pattern generici
        intent = await self._classify_generic_patterns(message_lower)
        if intent.type != "unknown":
            intent.retry_count = 5
            logger.info(f"[INTENT_CLASSIFIER] Intent trovato al retry 5: {intent.type} (confidence={intent.confidence:.2f})")
            return intent
        
        # Unknown dopo 5 retry
        logger.info(f"[INTENT_CLASSIFIER] Intent unknown dopo 5 retry")
        return Intent(type="unknown", confidence=0.0, parameters={}, retry_count=5)
    
    async def _classify_movements(self, message: str, strict: bool = True) -> Intent:
        """Classifica movimenti usando pattern esistenti da inventory_movements"""
        flags = 0 if strict else re.IGNORECASE
        
        # Consumi - usa pattern da movement_manager
        for pattern in self.movement_manager.consumo_patterns:
            match = re.search(pattern, message, flags)
            if match:
                quantity_str = match.group(1).strip()
                wine_name = match.group(2).strip()
                
                # Prova a convertire quantità (numero o parola)
                quantity = int(quantity_str) if quantity_str.isdigit() else self.word_to_number(quantity_str)
                if quantity is None:
                    continue
                
                return Intent(
                    type="movement_consumption",
                    confidence=0.9 if strict else 0.7,
                    parameters={"wine_name": wine_name, "quantity": quantity},
                    handler="register_consumption"
                )
        
        # Rifornimenti - usa pattern da movement_manager
        for pattern in self.movement_manager.rifornimento_patterns:
            match = re.search(pattern, message, flags)
            if match:
                quantity_str = match.group(1).strip()
                wine_name = match.group(2).strip()
                
                # Prova a convertire quantità (numero o parola)
                quantity = int(quantity_str) if quantity_str.isdigit() else self.word_to_number(quantity_str)
                if quantity is None:
                    continue
                
                return Intent(
                    type="movement_replenishment",
                    confidence=0.9 if strict else 0.7,
                    parameters={"wine_name": wine_name, "quantity": quantity},
                    handler="register_replenishment"
                )
        
        return Intent(type="unknown", confidence=0.0, parameters={})
    
    async def _classify_by_keywords(self, message: str) -> Intent:
        """Classifica usando keyword matching"""
        
        # Ricerca vini
        search_patterns = [
            r'\b(mostra|mostrami|dimmi|dammi|cerco|trova|quanti|quante)\s+(.*vino|.*vini)',
            r'\b(quanti|quante)\s+(.+?)\s+(?:ho|hai|ci sono|in cantina|in magazzino)',
            r'\b(quanto|quanto costa|prezzo)\s+(.+?)\s+(?:vendo|vendi|costano)',
        ]
        
        for pattern in search_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                search_term = match.group(2).strip() if len(match.groups()) >= 2 else ""
                return Intent(
                    type="search_wines",
                    confidence=0.8,
                    parameters={"search_term": search_term, "limit": 10},
                    handler="search_wines"
                )
        
        # Lista inventario
        if re.search(r'\b(lista|elenco|mostra|mostrami|vedi)\s+inventario', message, re.IGNORECASE):
            return Intent(
                type="inventory_list",
                confidence=0.9,
                parameters={},
                handler="get_inventory_list"
            )
        
        # Statistiche
        if re.search(r'\b(statistiche|riepilogo|totale|valore)\s+(inventario|vini)', message, re.IGNORECASE):
            return Intent(
                type="inventory_statistics",
                confidence=0.8,
                parameters={},
                handler="get_inventory_statistics"
            )
        
        # Scorte basse
        if re.search(r'\b(scorte\s+basse|vini\s+in\s+esaurimento|vini\s+quasi\s+finiti)', message, re.IGNORECASE):
            return Intent(
                type="low_stock_wines",
                confidence=0.8,
                parameters={"threshold": 5},
                handler="get_low_stock_wines"
            )
        
        return Intent(type="unknown", confidence=0.0, parameters={})
    
    def _normalize_text(self, text: str) -> str:
        """Normalizza testo rimuovendo punteggiatura e spazi multipli"""
        text = re.sub(r'[.,!?;:]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    async def _classify_generic_patterns(self, message: str) -> Intent:
        """Pattern generici (ultimo tentativo)"""
        # Pattern molto generici per catturare richieste comuni
        
        # "dimmi qualcosa su X" -> ricerca
        if re.search(r'\b(dimmi|dammi|mostra|mostrami)\s+(?:qualcosa\s+)?(?:su|di|del|della|dell\')\s+(.+)', message, re.IGNORECASE):
            match = re.search(r'\b(dimmi|dammi|mostra|mostrami)\s+(?:qualcosa\s+)?(?:su|di|del|della|dell\')\s+(.+)', message, re.IGNORECASE)
            if match:
                search_term = match.group(2).strip()
                return Intent(
                    type="search_wines",
                    confidence=0.6,
                    parameters={"search_term": search_term, "limit": 10},
                    handler="search_wines"
                )
        
        return Intent(type="unknown", confidence=0.0, parameters={})

