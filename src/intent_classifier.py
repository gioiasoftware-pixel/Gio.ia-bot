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
        
        # ✅ Cerca movimenti multipli (es. "ho consumato 3 chianti e ricevuto 3 amarone")
        movements = []
        
        # Pattern per separare movimenti multipli (e, poi, e anche, etc.)
        separators = r'\s+(?:e|poi|e\s+anche|,)\s+'
        parts = re.split(separators, message, flags=re.IGNORECASE)
        
        # Se ci sono più parti, prova a parsare ognuna come movimento
        if len(parts) > 1:
            # ✅ Strategia migliorata: cerca pattern movimento nel messaggio originale
            # per determinare tipo movimento (consumo/rifornimento)
            movement_type = None
            movement_verb = None
            
            # Cerca verbo movimento nel messaggio
            if re.search(r'\b(consumato|venduto|bevuto|consumo|vendo|bevo)\b', message, flags):
                movement_type = "consumption"
                movement_verb = "consumato"
            elif re.search(r'\b(ricevuto|comprato|aggiunto|rifornito|ricevo|compro|aggiungo)\b', message, flags):
                movement_type = "replenishment"
                movement_verb = "ricevuto"
            
            # Se non ho trovato verbo, prova pattern completi
            if not movement_type:
                for pattern in self.movement_manager.consumo_patterns:
                    if re.search(pattern, message, flags):
                        movement_type = "consumption"
                        break
                if not movement_type:
                    for pattern in self.movement_manager.rifornimento_patterns:
                        if re.search(pattern, message, flags):
                            movement_type = "replenishment"
                            break
            
            # Se ho trovato tipo movimento, parsare tutte le parti
            if movement_type:
                # Pattern per estrarre quantità e nome vino (migliorato per catturare anche "1 soave")
                # Es. "3 marlborough" → quantity=3, wine="marlborough"
                # Es. "1 soave" → quantity=1, wine="soave"
                # Es. "soave" → quantity=None, wine="soave"
                quantity_wine_pattern = r'^(\d+|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta|cento)\s+(.+)$'
                
                for i, part in enumerate(parts):
                    part = part.strip()
                    if not part:
                        continue
                    
                    # Rimuovi verbo movimento se presente (es. "ho consumato 3 marlborough" → "3 marlborough")
                    # Solo dalla prima parte
                    if i == 0:
                        part = re.sub(r'^(ho\s+)?(consumato|venduto|bevuto|ricevuto|comprato|aggiunto)\s+', '', part, flags=re.IGNORECASE).strip()
                    
                    # Prova a estrarre quantità e vino
                    match = re.search(quantity_wine_pattern, part, re.IGNORECASE)
                    if match:
                        quantity_str = match.group(1).strip()
                        wine_name = match.group(2).strip()
                        quantity = int(quantity_str) if quantity_str.isdigit() else self.word_to_number(quantity_str)
                        if quantity is not None and wine_name:
                            movements.append({
                                "type": movement_type,
                                "wine_name": wine_name,
                                "quantity": quantity
                            })
                            continue
                    
                    # Se non ha quantità, potrebbe essere solo nome vino
                    # Controlla se è un nome vino valido (almeno 3 caratteri, non parole comuni)
                    common_words = {'e', 'poi', 'anche', 'ho', 'consumato', 'ricevuto', 'comprato', 'aggiunto', 'venduto', 'bevuto', 'e', 'e anche'}
                    part_clean = part.lower().strip()
                    if len(part_clean) >= 3 and part_clean not in common_words:
                        # Usa quantità default 1 (o quantità del primo movimento se disponibile)
                        default_quantity = movements[0]["quantity"] if movements else 1
                        movements.append({
                            "type": movement_type,
                            "wine_name": part,  # Mantieni case originale
                            "quantity": default_quantity
                        })
            
            # Se ho trovato movimenti multipli, ritorna intent speciale
            if len(movements) > 1:
                return Intent(
                    type="multiple_movements",
                    confidence=0.95,
                    parameters={"movements": movements},
                    handler="register_multiple_movements"
                )
            elif len(movements) == 1:
                # Un solo movimento trovato, ritorna come movimento singolo
                m = movements[0]
                return Intent(
                    type="movement_consumption" if m["type"] == "consumption" else "movement_replenishment",
                    confidence=0.9 if strict else 0.7,
                    parameters={"wine_name": m["wine_name"], "quantity": m["quantity"]},
                    handler="register_consumption" if m["type"] == "consumption" else "register_replenishment"
                )
        
        # ✅ Se non ho trovato movimenti multipli, cerca movimento singolo (logica originale)
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
        
        # Tipi di vino comuni (per riconoscere quando usare filtri)
        wine_types = {
            'spumante': 'spumante', 'spumanti': 'spumante',
            'rosso': 'rosso', 'rossi': 'rosso',
            'bianco': 'bianco', 'bianchi': 'bianco',
            'rosato': 'rosato', 'rosati': 'rosato',
            'passito': 'passito', 'passiti': 'passito',
            'dolce': 'dolce', 'dolci': 'dolce',
        }
        
        # Paesi e sinonimi (per riconoscere filtri geografici)
        country_synonyms = {
            'italia': 'Italia', 'italiano': 'Italia', 'italiani': 'Italia', 'italiane': 'Italia',
            'italy': 'Italia',
            'francia': 'Francia', 'francese': 'Francia', 'francesi': 'Francia',
            'france': 'Francia',
            'spagna': 'Spagna', 'spagnolo': 'Spagna', 'spagnoli': 'Spagna',
            'spain': 'Spagna',
            'usa': 'USA', 'stati uniti': 'USA', 'stati uniti d\'america': 'USA', 'america': 'USA',
            'united states': 'USA', 'us': 'USA',
            'germania': 'Germania', 'tedesco': 'Germania', 'tedeschi': 'Germania',
            'germany': 'Germania',
            'portogallo': 'Portogallo', 'portoghese': 'Portogallo', 'portoghesi': 'Portogallo',
            'portugal': 'Portogallo',
            'australia': 'Australia', 'australiano': 'Australia', 'australiani': 'Australia',
            'cile': 'Cile', 'cileno': 'Cile', 'cileni': 'Cile',
            'chile': 'Cile',
            'argentina': 'Argentina', 'argentino': 'Argentina', 'argentini': 'Argentina',
        }
        
        # Regioni italiane comuni
        italian_regions = {
            'toscana': 'Toscana', 'toscano': 'Toscana', 'toscani': 'Toscana',
            'piemonte': 'Piemonte', 'piemontese': 'Piemonte', 'piemontesi': 'Piemonte',
            'veneto': 'Veneto', 'veneto': 'Veneto', 'veneti': 'Veneto',
            'lombardia': 'Lombardia', 'lombardo': 'Lombardia', 'lombardi': 'Lombardia',
            'emilia': 'Emilia-Romagna', 'emilia romagna': 'Emilia-Romagna', 'emiliano': 'Emilia-Romagna',
            'umbria': 'Umbria', 'umbro': 'Umbria', 'umbri': 'Umbria',
            'marche': 'Marche', 'marchigiano': 'Marche', 'marchigiani': 'Marche',
            'abruzzo': 'Abruzzo', 'abruzzese': 'Abruzzo', 'abruzzesi': 'Abruzzo',
            'campania': 'Campania', 'campano': 'Campania', 'campani': 'Campania',
            'puglia': 'Puglia', 'pugliese': 'Puglia', 'pugliesi': 'Puglia',
            'sicilia': 'Sicilia', 'siciliano': 'Sicilia', 'siciliani': 'Sicilia',
            'sardegna': 'Sardegna', 'sardo': 'Sardegna', 'sardi': 'Sardegna',
        }
        
        # Ricerca vini con pattern "quanti X ho?"
        quantity_pattern = r'\b(quanti|quante)\s+(.+?)\s+(?:ho|hai|ci sono|in cantina|in magazzino)'
        match = re.search(quantity_pattern, message, re.IGNORECASE)
        if match:
            search_term = match.group(2).strip().lower()
            filters = {}
            
            # Controlla se è un tipo di vino comune
            if search_term in wine_types:
                filters["wine_type"] = wine_types[search_term]
                return Intent(
                    type="search_wines",
                    confidence=0.9,
                    parameters={"filters": filters, "limit": 50},
                    handler="search_wines"
                )
            
            # Controlla se contiene un paese
            for synonym, country in country_synonyms.items():
                if synonym in search_term:
                    filters["country"] = country
                    break
            
            # Controlla se contiene una regione italiana
            for synonym, region in italian_regions.items():
                if synonym in search_term:
                    filters["region"] = region
                    break
            
            # Se ha filtri, usali
            if filters:
                return Intent(
                    type="search_wines",
                    confidence=0.9,
                    parameters={"filters": filters, "limit": 50},
                    handler="search_wines"
                )
            
            # Altrimenti usa search_term normale (l'AI interpreterà meglio)
            return Intent(
                type="unknown",  # ✅ Passa all'AI per interpretazione migliore
                confidence=0.0,
                parameters={}
            )
        
        # Pattern "che X ho?" dove X può essere tipo vino, paese, regione (es. "che rossi ho?", "che bianchi ho?")
        che_pattern = r'\b(che|quali)\s+(.+?)\s+(?:ho|hai|ci sono|in cantina|in magazzino)'
        match = re.search(che_pattern, message, re.IGNORECASE)
        if match:
            descriptor = match.group(2).strip().lower()
            filters = {}
            
            # Controlla tipo di vino
            if descriptor in wine_types:
                filters["wine_type"] = wine_types[descriptor]
                return Intent(
                    type="search_wines",
                    confidence=0.95,  # Alta confidenza per pattern "che X ho?"
                    parameters={"filters": filters, "limit": 50},
                    handler="search_wines"
                )
            
            # Controlla paese
            for synonym, country in country_synonyms.items():
                if synonym in descriptor:
                    filters["country"] = country
                    return Intent(
                        type="search_wines",
                        confidence=0.95,
                        parameters={"filters": filters, "limit": 50},
                        handler="search_wines"
                    )
            
            # Controlla regione
            for synonym, region in italian_regions.items():
                if synonym in descriptor:
                    filters["region"] = region
                    return Intent(
                        type="search_wines",
                        confidence=0.95,
                        parameters={"filters": filters, "limit": 50},
                        handler="search_wines"
                    )
            
            # Se non riconosce, passa all'AI
            return Intent(type="unknown", confidence=0.0, parameters={})
        
        # Pattern "vini X" o "X vini" (es. "vini italiani", "vini della toscana")
        wine_pattern = r'\b(vini|vino)\s+(.+?)(?:\s|$)'
        match = re.search(wine_pattern, message, re.IGNORECASE)
        if match:
            descriptor = match.group(2).strip().lower()
            filters = {}
            
            # Controlla tipo di vino
            if descriptor in wine_types:
                filters["wine_type"] = wine_types[descriptor]
            
            # Controlla paese
            for synonym, country in country_synonyms.items():
                if synonym in descriptor:
                    filters["country"] = country
                    break
            
            # Controlla regione
            for synonym, region in italian_regions.items():
                if synonym in descriptor:
                    filters["region"] = region
                    break
            
            if filters:
                return Intent(
                    type="search_wines",
                    confidence=0.9,
                    parameters={"filters": filters, "limit": 50},
                    handler="search_wines"
                )
            # Se non riconosce, passa all'AI
            return Intent(type="unknown", confidence=0.0, parameters={})
        
        # Altri pattern di ricerca
        search_patterns = [
            r'\b(mostra|mostrami|dimmi|dammi|cerco|trova)\s+(.*vino|.*vini)',
            r'\b(quanto|quanto costa|prezzo)\s+(.+?)\s+(?:vendo|vendi|costano)',
        ]
        
        for pattern in search_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                search_term = match.group(2).strip() if len(match.groups()) >= 2 else ""
                search_term_lower = search_term.lower()
                filters = {}
                
                # Controlla tipo di vino
                if search_term_lower in wine_types:
                    filters["wine_type"] = wine_types[search_term_lower]
                
                # Controlla paese
                for synonym, country in country_synonyms.items():
                    if synonym in search_term_lower:
                        filters["country"] = country
                        break
                
                # Controlla regione
                for synonym, region in italian_regions.items():
                    if synonym in search_term_lower:
                        filters["region"] = region
                        break
                
                if filters:
                    return Intent(
                        type="search_wines",
                        confidence=0.9,
                        parameters={"filters": filters, "limit": 50},
                        handler="search_wines"
                    )
                
                # Se non riconosce, passa all'AI per interpretazione migliore
                return Intent(type="unknown", confidence=0.0, parameters={})
        
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

