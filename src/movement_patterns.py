"""
Pattern condivisi per riconoscimento movimenti inventario.
Centralizza tutta la logica di pattern matching per evitare duplicazione.
"""
import re
from typing import List, Tuple, Optional, Dict, Any


def word_to_number(word: str) -> Optional[int]:
    """
    Converte numero in lettere italiano in numero intero.
    Supporta numeri comuni da 1 a 20 e multipli di 10 fino a 100.
    """
    word_lower = word.lower().strip()
    
    numbers_map = {
        'un': 1, 'uno': 1, 'una': 1,
        'due': 2, 'tre': 3, 'quattro': 4, 'cinque': 5,
        'sei': 6, 'sette': 7, 'otto': 8, 'nove': 9,
        'dieci': 10, 'undici': 11, 'dodici': 12,
        'tredici': 13, 'quattordici': 14, 'quindici': 15,
        'sedici': 16, 'diciassette': 17, 'diciotto': 18,
        'diciannove': 19, 'venti': 20,
        'trenta': 30, 'quaranta': 40, 'cinquanta': 50,
        'sessanta': 60, 'settanta': 70, 'ottanta': 80,
        'novanta': 90, 'cento': 100
    }
    
    return numbers_map.get(word_lower)


# Pattern condivisi per riconoscere movimenti
NUMBER_PATTERN = r'(\d+|un|uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|novanta|cento)'

# Pattern consumo (ordinati dalla più specifica alla più generica)
CONSUMO_PATTERNS = [
    r'ho venduto ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho consumato ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho bevuto ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho venduto ' + NUMBER_PATTERN + r' (.+)',
    r'ho consumato ' + NUMBER_PATTERN + r' (.+)',
    r'ho bevuto ' + NUMBER_PATTERN + r' (.+)',
    r'venduto ' + NUMBER_PATTERN + r' (.+)',
    r'consumato ' + NUMBER_PATTERN + r' (.+)',
    r'bevuto ' + NUMBER_PATTERN + r' (.+)',
    NUMBER_PATTERN + r' bottiglie? di (.+) vendute?',
    NUMBER_PATTERN + r' bottiglie? di (.+) consumate?',
    NUMBER_PATTERN + r' bottiglie? di (.+) bevute?'
]

# Pattern rifornimento (ordinati dalla più specifica alla più generica)
RIFORNIMENTO_PATTERNS = [
    r'ho ricevuto ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho comprato ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho aggiunto ' + NUMBER_PATTERN + r' bottiglie? di (.+)',
    r'ho ricevuto ' + NUMBER_PATTERN + r' (.+)',
    r'ho comprato ' + NUMBER_PATTERN + r' (.+)',
    r'ho aggiunto ' + NUMBER_PATTERN + r' (.+)',
    r'ricevuto ' + NUMBER_PATTERN + r' (.+)',
    r'comprato ' + NUMBER_PATTERN + r' (.+)',
    r'aggiunto ' + NUMBER_PATTERN + r' (.+)',
    NUMBER_PATTERN + r' bottiglie? di (.+) ricevute?',
    NUMBER_PATTERN + r' bottiglie? di (.+) comprate?',
    NUMBER_PATTERN + r' bottiglie? di (.+) aggiunte?'
]

# Pattern semplici per numeri interi (usati in ai.py per compatibilità)
CONSUMO_PATTERNS_SIMPLE = [
    r'ho venduto (\d+) bottiglie? di (.+)',
    r'ho consumato (\d+) bottiglie? di (.+)',
    r'ho bevuto (\d+) bottiglie? di (.+)',
    r'ho venduto (\d+) (.+)',
    r'ho consumato (\d+) (.+)',
    r'ho bevuto (\d+) (.+)',
    r'venduto (\d+) (.+)',
    r'consumato (\d+) (.+)',
    r'bevuto (\d+) (.+)',
]

RIFORNIMENTO_PATTERNS_SIMPLE = [
    r'ho ricevuto (\d+) bottiglie? di (.+)',
    r'ho comprato (\d+) bottiglie? di (.+)',
    r'ho aggiunto (\d+) bottiglie? di (.+)',
    r'ho ricevuto (\d+) (.+)',
    r'ho comprato (\d+) (.+)',
    r'ho aggiunto (\d+) (.+)',
    r'ricevuto (\d+) (.+)',
    r'comprato (\d+) (.+)',
    r'aggiunto (\d+) (.+)',
]


def parse_movement_pattern(message_text: str, patterns: List[str], allow_word_numbers: bool = True) -> Optional[Tuple[str, int, str]]:
    """
    Cerca un pattern movimento nel messaggio.
    
    Args:
        message_text: Testo del messaggio
        patterns: Lista di pattern regex da provare
        allow_word_numbers: Se True, supporta numeri in lettere
    
    Returns:
        Tuple (movement_type, quantity, wine_name) o None se non trovato
    """
    message_lower = message_text.lower().strip()
    
    for pattern in patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            quantity_str = match.group(1).strip()
            
            # Converti quantità
            if quantity_str.isdigit():
                quantity = int(quantity_str)
            elif allow_word_numbers:
                quantity = word_to_number(quantity_str)
                if quantity is None:
                    continue
            else:
                continue
            
            wine_name = match.group(2).strip()
            return quantity, wine_name
    
    return None


def extract_price_filters(message_text: str) -> Dict[str, Optional[float]]:
    """
    Estrae filtri di prezzo/costo dal messaggio.
    Supporta pattern come:
    - "intorno a 40€", "circa 40€", "a 40€"
    - "sotto i 30€", "meno di 30€", "sotto 30€"
    - "sopra i 50€", "più di 50€", "oltre 50€"
    - "tra i 50 e i 100€", "da 50 a 100€", "tra 50-100€"
    
    Returns:
        Dict con 'price_min', 'price_max', 'cost_min', 'cost_max', 'price_around', 'cost_around'
    """
    filters = {
        'price_min': None,
        'price_max': None,
        'cost_min': None,
        'cost_max': None,
        'price_around': None,
        'cost_around': None
    }
    
    message_lower = message_text.lower()
    
    # Pattern per estrarre numeri con € o euro
    price_pattern = r'(\d+(?:[.,]\d+)?)\s*(?:€|euro|eur)'
    
    # Pattern "intorno a X€" o "circa X€" o "a X€" (prezzo vendita)
    around_patterns = [
        r'(?:intorno\s+a|circa|a)\s+' + price_pattern + r'(?:\s+di\s+prezzo|\s+di\s+vendita|\s+prezzo)?',
        r'prezzo\s+(?:di\s+)?vendita\s+(?:intorno\s+a|circa|a)\s+' + price_pattern,
    ]
    for pattern in around_patterns:
        match = re.search(pattern, message_lower)
        if match:
            price = float(match.group(1).replace(',', '.'))
            filters['price_around'] = price
            # Range intorno: ±10% o ±5€ (il maggiore)
            tolerance = max(price * 0.1, 5.0)
            filters['price_min'] = price - tolerance
            filters['price_max'] = price + tolerance
            break
    
    # Pattern "sotto i X€" o "meno di X€" (prezzo vendita)
    under_patterns = [
        r'(?:sotto\s+i|sotto|meno\s+di|inferiore\s+a)\s+' + price_pattern + r'(?:\s+di\s+prezzo|\s+di\s+vendita)?',
        r'prezzo\s+(?:di\s+)?vendita\s+(?:sotto\s+i|sotto|meno\s+di|inferiore\s+a)\s+' + price_pattern,
    ]
    for pattern in under_patterns:
        match = re.search(pattern, message_lower)
        if match:
            price = float(match.group(1).replace(',', '.'))
            if filters['price_max'] is None or price < filters['price_max']:
                filters['price_max'] = price
            break
    
    # Pattern "sopra i X€" o "più di X€" (prezzo vendita)
    over_patterns = [
        r'(?:sopra\s+i|sopra|pi[ùu]\s+di|oltre|superiore\s+a)\s+' + price_pattern + r'(?:\s+di\s+prezzo|\s+di\s+vendita)?',
        r'prezzo\s+(?:di\s+)?vendita\s+(?:sopra\s+i|sopra|pi[ùu]\s+di|oltre|superiore\s+a)\s+' + price_pattern,
    ]
    for pattern in over_patterns:
        match = re.search(pattern, message_lower)
        if match:
            price = float(match.group(1).replace(',', '.'))
            if filters['price_min'] is None or price > filters['price_min']:
                filters['price_min'] = price
            break
    
    # Pattern "tra X e Y€" o "da X a Y€" (prezzo vendita)
    range_patterns = [
        r'tra\s+(?:i\s+)?' + price_pattern + r'\s+e\s+(?:i\s+)?' + price_pattern + r'(?:\s+di\s+prezzo|\s+di\s+vendita)?',
        r'da\s+' + price_pattern + r'\s+a\s+' + price_pattern + r'(?:\s+di\s+prezzo|\s+di\s+vendita)?',
        r'prezzo\s+(?:di\s+)?vendita\s+tra\s+(?:i\s+)?' + price_pattern + r'\s+e\s+(?:i\s+)?' + price_pattern,
    ]
    for pattern in range_patterns:
        match = re.search(pattern, message_lower)
        if match:
            price1 = float(match.group(1).replace(',', '.'))
            price2 = float(match.group(2).replace(',', '.'))
            filters['price_min'] = min(price1, price2)
            filters['price_max'] = max(price1, price2)
            break
    
    # Pattern simili per costo acquisto
    # "costo intorno a X€", "costo sotto X€", ecc.
    cost_around_patterns = [
        r'costo\s+(?:di\s+)?acquisto\s+(?:intorno\s+a|circa|a)\s+' + price_pattern,
        r'costo\s+(?:intorno\s+a|circa|a)\s+' + price_pattern,
    ]
    for pattern in cost_around_patterns:
        match = re.search(pattern, message_lower)
        if match:
            cost = float(match.group(1).replace(',', '.'))
            filters['cost_around'] = cost
            tolerance = max(cost * 0.1, 5.0)
            filters['cost_min'] = cost - tolerance
            filters['cost_max'] = cost + tolerance
            break
    
    cost_under_patterns = [
        r'costo\s+(?:di\s+)?acquisto\s+(?:sotto\s+i|sotto|meno\s+di)\s+' + price_pattern,
        r'costo\s+(?:sotto\s+i|sotto|meno\s+di)\s+' + price_pattern,
    ]
    for pattern in cost_under_patterns:
        match = re.search(pattern, message_lower)
        if match:
            cost = float(match.group(1).replace(',', '.'))
            if filters['cost_max'] is None or cost < filters['cost_max']:
                filters['cost_max'] = cost
            break
    
    cost_over_patterns = [
        r'costo\s+(?:di\s+)?acquisto\s+(?:sopra\s+i|sopra|pi[ùu]\s+di)\s+' + price_pattern,
        r'costo\s+(?:sopra\s+i|sopra|pi[ùu]\s+di)\s+' + price_pattern,
    ]
    for pattern in cost_over_patterns:
        match = re.search(pattern, message_lower)
        if match:
            cost = float(match.group(1).replace(',', '.'))
            if filters['cost_min'] is None or cost > filters['cost_min']:
                filters['cost_min'] = cost
            break
    
    cost_range_patterns = [
        r'costo\s+(?:di\s+)?acquisto\s+tra\s+(?:i\s+)?' + price_pattern + r'\s+e\s+(?:i\s+)?' + price_pattern,
        r'costo\s+tra\s+(?:i\s+)?' + price_pattern + r'\s+e\s+(?:i\s+)?' + price_pattern,
    ]
    for pattern in cost_range_patterns:
        match = re.search(pattern, message_lower)
        if match:
            cost1 = float(match.group(1).replace(',', '.'))
            cost2 = float(match.group(2).replace(',', '.'))
            filters['cost_min'] = min(cost1, cost2)
            filters['cost_max'] = max(cost1, cost2)
            break
    
    return filters


def parse_single_movement(message_text: str) -> Optional[Tuple[str, int, str, Dict[str, Optional[float]]]]:
    """
    Cerca un movimento singolo nel messaggio (consumo o rifornimento).
    Estrae anche filtri di prezzo/costo se presenti.
    
    Returns:
        Tuple (movement_type, quantity, wine_name, price_filters) o None
    """
    # Estrai filtri di prezzo prima di processare il movimento
    price_filters = extract_price_filters(message_text)
    
    # Prova prima i consumi
    result = parse_movement_pattern(message_text, CONSUMO_PATTERNS)
    if result:
        quantity, wine_name = result
        return ('consumo', quantity, wine_name, price_filters)
    
    # Poi i rifornimenti
    result = parse_movement_pattern(message_text, RIFORNIMENTO_PATTERNS)
    if result:
        quantity, wine_name = result
        return ('rifornimento', quantity, wine_name, price_filters)
    
    return None


def parse_multiple_movements(message_text: str, movement_type: str) -> List[Tuple[int, str]]:
    """
    Analizza un messaggio per trovare movimenti multipli.
    Esempio: "ho consumato 1 etna e 1 fiano" -> [(1, "etna"), (1, "fiano")]
    Supporta anche formati con newline e vari prefissi.
    
    Args:
        message_text: Testo del messaggio
        movement_type: 'consumo' o 'rifornimento'
    
    Returns:
        Lista di tuple (quantity, wine_name)
    """
    movements = []
    message_lower = message_text.lower().strip()
    
    # Pattern per riconoscere il prefisso del movimento (estesi)
    if movement_type == 'consumo':
        prefix_patterns = [
            r'ho venduto|ho consumato|ho bevuto',
            r'venduto|consumato|bevuto'
        ]
    else:
        # Supporta anche "aggiungere:" come prefisso
        prefix_patterns = [
            r'aggiungere\s*:',
            r'ho ricevuto|ho comprato|ho aggiunto',
            r'ricevuto|comprato|aggiunto'
        ]
    
    # Cerca il prefisso
    prefix_match = None
    for prefix_pattern in prefix_patterns:
        prefix_match = re.search(prefix_pattern, message_lower, re.IGNORECASE)
        if prefix_match:
            break
    
    # Se c'è un prefisso, estrai parte dopo
    if prefix_match:
        prefix_end = prefix_match.end()
        rest_of_message = message_lower[prefix_end:].strip()
    else:
        # Se non c'è prefisso, usa tutto il messaggio (potrebbe essere solo numeri e vini)
        rest_of_message = message_lower
    
    # Normalizza: sostituisci newline e virgole con " e " per unificare separatori
    rest_of_message = re.sub(r'[\n,;]+', ' e ', rest_of_message)
    
    # Split per " e " per trovare movimenti multipli (supporta anche "e" singolo)
    parts = re.split(r'\s+e\s+', rest_of_message)
    
    # Pattern per riconoscere un singolo movimento: numero + (bottiglie di)? + nome vino
    # NUMBER_PATTERN è già un gruppo: (\d+|un|uno|...)
    movement_pattern = rf'^{NUMBER_PATTERN}\s+(?:bottiglie?\s+di\s+)?(.+)$'
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Prova pattern completo
        match = re.match(movement_pattern, part, re.IGNORECASE)
        if match:
            quantity_str = match.group(1).strip()
            
            # Converti quantità
            if quantity_str.isdigit():
                quantity = int(quantity_str)
            else:
                quantity = word_to_number(quantity_str)
                if quantity is None:
                    continue
            
            wine_name = match.group(2).strip()
            # Rimuovi punteggiatura finale comune
            wine_name = re.sub(r'[,.;]+$', '', wine_name).strip()
            if wine_name:
                movements.append((quantity, wine_name))
    
    return movements
