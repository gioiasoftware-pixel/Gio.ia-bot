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


def parse_single_movement(message_text: str) -> Optional[Tuple[str, int, str]]:
    """
    Cerca un movimento singolo nel messaggio (consumo o rifornimento).
    
    Returns:
        Tuple (movement_type, quantity, wine_name) o None
    """
    # Prova prima i consumi
    result = parse_movement_pattern(message_text, CONSUMO_PATTERNS)
    if result:
        quantity, wine_name = result
        return ('consumo', quantity, wine_name)
    
    # Poi i rifornimenti
    result = parse_movement_pattern(message_text, RIFORNIMENTO_PATTERNS)
    if result:
        quantity, wine_name = result
        return ('rifornimento', quantity, wine_name)
    
    return None


def parse_multiple_movements(message_text: str, movement_type: str) -> List[Tuple[int, str]]:
    """
    Analizza un messaggio per trovare movimenti multipli.
    Esempio: "ho consumato 1 etna e 1 fiano" -> [(1, "etna"), (1, "fiano")]
    
    Args:
        message_text: Testo del messaggio
        movement_type: 'consumo' o 'rifornimento'
    
    Returns:
        Lista di tuple (quantity, wine_name)
    """
    movements = []
    message_lower = message_text.lower().strip()
    
    # Pattern per riconoscere il prefisso del movimento
    if movement_type == 'consumo':
        prefix_patterns = [
            r'ho venduto|ho consumato|ho bevuto|venduto|consumato|bevuto',
            r'ho venduto|ho consumato|ho bevuto'
        ]
    else:
        prefix_patterns = [
            r'ho ricevuto|ho comprato|ho aggiunto|ricevuto|comprato|aggiunto',
            r'ho ricevuto|ho comprato|ho aggiunto'
        ]
    
    # Cerca il prefisso
    prefix_match = None
    for prefix_pattern in prefix_patterns:
        prefix_match = re.search(prefix_pattern, message_lower, re.IGNORECASE)
        if prefix_match:
            break
    
    if not prefix_match:
        return movements
    
    # Estrai parte dopo il prefisso
    prefix_end = prefix_match.end()
    rest_of_message = message_lower[prefix_end:].strip()
    
    # Split per " e " per trovare movimenti multipli
    parts = re.split(r'\s+e\s+', rest_of_message)
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Pattern: numero + (bottiglie di)? + nome vino
        match = re.match(rf'^{NUMBER_PATTERN}\s+(?:bottiglie?\s+di\s+)?(.+)$', part, re.IGNORECASE)
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
            movements.append((quantity, wine_name))
    
    return movements
