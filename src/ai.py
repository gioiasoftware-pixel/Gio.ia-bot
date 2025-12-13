import logging
import os
import re
import asyncio
from typing import Optional, Any, Dict, List
from openai import OpenAI, OpenAIError
from .config import OPENAI_MODEL
from .database_async import async_db_manager
from .response_templates import (
    format_inventory_list, format_wine_quantity, format_wine_price,
    format_wine_info, format_wine_not_found, format_wine_exists,
    format_low_stock_alert, format_inventory_summary, format_movement_period_summary,
    format_search_no_results
)
from .database_async import get_movement_summary

# Carica direttamente la variabile ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Disabilita eventuali proxy automatici che potrebbero causare conflitti
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

logger = logging.getLogger(__name__)


def _is_general_conversation(prompt: str) -> bool:
    """
    Rileva se la domanda è una conversazione generale NON relativa all'inventario/vini.
    Se è una domanda generale, deve essere passata all'AI senza cercare vini.
    """
    p = prompt.lower().strip()
    
    # Pattern per domande generali sul bot
    general_patterns = [
        r'\b(chi\s+sei|cosa\s+fai|parlami\s+di\s+te|cosa\s+puoi\s+fare|dimmi\s+di\s+te|raccontami\s+di\s+te)',
        r'\b(aiuto|help|assistenza|supporto)',
        r'\b(ciao|salve|buongiorno|buonasera|buonanotte)',
        r'\b(grazie|prego|perfetto|ok|va bene)',
        r'\b(come\s+stai|come\s+va|tutto\s+bene)',
    ]
    
    # Se matcha pattern generali E non contiene termini relativi a vini/inventario
    wine_related_keywords = [
        'vino', 'vini', 'bottiglia', 'bottiglie', 'inventario', 'cantina', 'magazzino',
        'consumo', 'consumi', 'rifornimento', 'rifornimenti', 'venduto', 'comprato',
        'barolo', 'chianti', 'brunello', 'amarone', 'prosecco', 'champagne',
        'prezzo', 'quantità', 'annata', 'produttore', 'regione', 'toscana', 'piemonte'
    ]
    
    # Controlla se contiene pattern generali
    has_general_pattern = any(re.search(pt, p) for pt in general_patterns)
    
    # Controlla se NON contiene termini relativi a vini
    has_wine_keywords = any(kw in p for kw in wine_related_keywords)
    
    # Se ha pattern generali E non ha keyword vini, è una conversazione generale
    if has_general_pattern and not has_wine_keywords:
        return True
    
    # Se è una domanda molto corta senza keyword vini, probabilmente è generale
    if len(p.split()) <= 5 and not has_wine_keywords:
        # Controlla se contiene parole comuni di domande generali
        general_words = ['chi', 'cosa', 'come', 'perché', 'quando', 'dove', 'perché']
        if any(word in p for word in general_words):
            return True
    
    return False


def _is_inventory_list_request(prompt: str) -> bool:
    """
    Riconosce richieste tipo: che vini ho? elenco/lista inventario, mostra inventario, ecc.
    IMPORTANTE: NON matchare se la richiesta contiene filtri (region, tipo, paese, prezzo) -
    in quel caso passa all'AI che userà search_wines.
    """
    p = prompt.lower().strip()
    
    # Se contiene filtri, NON è una richiesta lista semplice → passa all'AI
    filter_keywords = [
        'della', 'del', 'dello', 'delle', 'degli', 'di', 'itali', 'frances', 'spagnol', 'tedesc',
        'toscana', 'piemonte', 'veneto', 'sicilia', 'rosso', 'bianco', 'spumante', 'rosato',
        'prezzo', 'annata', 'produttore', 'cantina', 'azienda'
    ]
    if any(kw in p for kw in filter_keywords):
        return False  # Passa all'AI con search_wines
    
    patterns = [
        r"\bche\s+vini\s+ho\b",
        r"\bquanti\s+vini\s+ho\b",
        r"\bquante\s+vini\s+ho\b",
        r"\bquanti\s+vini\s+hai\b",
        r"\bquante\s+vini\s+hai\b",
        r"\bche\s+vini\s+hai\b",
        r"\bquali\s+vini\s+ho\b",
        r"\bquali\s+vini\s+hai\b",
        r"\belenco\s+vini\b",
        r"\blista\s+vini\b",
        r"\bmostra\s+inventario\b",
        r"\bvedi\s+inventario\b",
        r"\bmostra\s+i\s+vini\b",
        r"\bmostrami\s+i\s+vini\b",
        r"\bmostrami\s+inventario\b",
        r"\bmostra\s+tutti\s+i\s+vini\b",
        r"\binventario\s+completo\b",
        r"\binventario\b",
    ]
    return any(re.search(pt, p) for pt in patterns)


def _is_add_wine_request(prompt: str) -> bool:
    """
    Riconosce richieste di aggiungere un vino.
    Pattern: aggiungi vino, aggiungere vino, nuovo vino, inserisci vino, ecc.
    """
    p = prompt.lower().strip()
    
    patterns = [
        r"\baggiungi\s+(?:un\s+)?vino\b",
        r"\baggiungere\s+(?:un\s+)?vino\b",
        r"\binserisci\s+(?:un\s+)?vino\b",
        r"\binserire\s+(?:un\s+)?vino\b",
        r"\bnuovo\s+vino\b",
        r"\bregistra\s+(?:un\s+)?vino\b",
        r"\bregistrare\s+(?:un\s+)?vino\b",
        r"\bcrea\s+(?:un\s+)?vino\b",
        r"\bcreare\s+(?:un\s+)?vino\b",
        r"\badd\s+wine\b",  # Inglese
        r"\bnew\s+wine\b",  # Inglese
    ]
    return any(re.search(pt, p) for pt in patterns)


def _is_movement_summary_request(prompt: str) -> tuple[bool, Optional[str]]:
    """
    Riconosce richieste tipo: ultimi consumi/movimenti/ricavi.
    Ritorna (is_request, period) dove period può essere 'day', 'week', 'month', o 'yesterday'.
    """
    p = prompt.lower().strip()
    
    # Controlla prima per richieste specifiche con date
    # Richieste consumo ieri
    if any(re.search(pt, p) for pt in [
        r"\b(consumato|consumi|consumate)\s+(ieri|il\s+giorno\s+prima)\b",
        r"\bvini\s+(consumato|consumi|consumate)\s+ieri\b",
        r"\b(che\s+)?vini\s+ho\s+consumato\s+ieri\b",
        r"\b(che\s+)?vini\s+hai\s+consumato\s+ieri\b",
        r"\bconsumi\s+(di|del)\s+ieri\b",
        r"\b(ieri|il\s+giorno\s+prima)\s+(ho|hai)\s+consumato\b",
    ]):
        return (True, 'yesterday')
    
    # Richieste rifornimenti/arrivati/ricevuti ieri (DEVE essere prima di pattern più generici)
    # Pattern più specifici prima - rimuovo \b alla fine per gestire punteggiatura
    if any(re.search(pt, p) for pt in [
        r"\b(che\s+)?vini\s+(mi\s+sono\s+)?(arrivati|ricevuti|riforniti)\s+ieri",
        r"\b(che\s+)?vini\s+ho\s+(ricevuto|rifornito)\s+ieri",
        r"\bvini\s+(mi\s+sono\s+)?arrivati\s+ieri",
        r"\b(ieri|il\s+giorno\s+prima)\s+(sono\s+arrivati|ho\s+ricevuto|ho\s+rifornito)",
        r"\brifornimenti\s+(di|del)\s+ieri",
        r"\b(arrivati|arrivate|arrivato|ricevuti|ricevute|ricevuto|riforniti|rifornite|rifornito)\s+(ieri|il\s+giorno\s+prima)",
    ]):
        return (True, 'yesterday_replenished')
    
    # Richieste movimenti generici di ieri
    if any(re.search(pt, p) for pt in [
        r"\bmovimenti\s+(di|del)\s+ieri\b",
    ]):
        return (True, 'yesterday')
    
    # Pattern generici (senza data specifica)
    if any(re.search(pt, p) for pt in [
        r"\bultimi\s+consumi\b",
        r"\bultimi\s+movimenti\b",
        r"\bconsumi\s+recenti\b",
        r"\bmovimenti\s+recenti\b",
        r"\bmi\s+dici\s+i\s+miei\s+ultimi\s+consumi\b",
        r"\bmi\s+dici\s+gli\s+ultimi\s+miei\s+consumi\b",
        r"\bultimi\s+miei\s+consumi\b",
        r"\bmostra\s+(ultimi|recenti)\s+(consumi|movimenti)\b",
        r"\briepilogo\s+(consumi|movimenti)\b",
    ]):
        return (True, None)  # Period non specificato, chiedi all'utente
    
    return (False, None)


def _is_informational_query(prompt: str) -> tuple[Optional[str], Optional[str]]:
    """
    Riconosce domande informative generiche sul vino.
    Ritorna (query_type, field) dove:
    - query_type: 'min' o 'max'
    - field: 'quantity', 'selling_price', 'cost_price', 'vintage'
    
    Esempi:
    - "quale vino ha meno quantità" → ('min', 'quantity')
    - "quale è il più costoso" → ('max', 'selling_price')
    - "quale ha più bottiglie" → ('max', 'quantity')
    """
    p = prompt.lower().strip()
    
    # Pattern per quantità (min)
    min_quantity_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:ha|con)\s+(?:meno|minore|minima)\s+(?:quantit[àa]|bottiglie)",
        r"quale\s+è\s+il\s+(?:vino|bottiglia)\s+(?:con|che\s+ha)\s+(?:meno|minore|minima)\s+(?:quantit[àa]|bottiglie)",
        r"(?:vino|bottiglia)\s+(?:con|che\s+ha)\s+(?:meno|minore|minima)\s+(?:quantit[àa]|bottiglie)",
        r"(?:meno|minore|minima)\s+(?:quantit[àa]|bottiglie)",
    ]
    
    # Pattern per quantità (max)
    max_quantity_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:ha|con)\s+(?:pi[ùu]|maggiore|massima)\s+(?:quantit[àa]|bottiglie)",
        r"quale\s+è\s+il\s+(?:vino|bottiglia)\s+(?:con|che\s+ha)\s+(?:pi[ùu]|maggiore|massima)\s+(?:quantit[àa]|bottiglie)",
        r"(?:vino|bottiglia)\s+(?:con|che\s+ha)\s+(?:pi[ùu]|maggiore|massima)\s+(?:quantit[àa]|bottiglie)",
        r"(?:pi[ùu]|maggiore|massima)\s+(?:quantit[àa]|bottiglie)",
    ]
    
    # Pattern per prezzo vendita (max - più costoso)
    max_price_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?costos[oa]",
        r"quale\s+è\s+il\s+(?:vino|bottiglia)\s+(?:pi[ùu]\s+)?costos[oa]",
        r"(?:vino|bottiglia)\s+(?:pi[ùu]\s+)?costos[oa]",
        r"quale\s+(?:vino|bottiglia)\s+costa\s+di\s+pi[ùu]",
        r"quale\s+(?:vino|bottiglia)\s+ha\s+il\s+prezzo\s+(?:pi[ùu]\s+)?alto",
        r"(?:pi[ùu]\s+)?costos[oa]",
    ]
    
    # Pattern per prezzo vendita (min - più economico)
    min_price_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?economic[oa]",
        r"quale\s+è\s+il\s+(?:vino|bottiglia)\s+(?:pi[ùu]\s+)?economic[oa]",
        r"(?:vino|bottiglia)\s+(?:pi[ùu]\s+)?economic[oa]",
        r"quale\s+(?:vino|bottiglia)\s+costa\s+di\s+meno",
        r"quale\s+(?:vino|bottiglia)\s+ha\s+il\s+prezzo\s+(?:pi[ùu]\s+)?basso",
        r"(?:pi[ùu]\s+)?economic[oa]",
    ]
    
    # Pattern per prezzo acquisto (max)
    max_cost_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?costos[oa]\s+(?:da\s+)?acquist[oa]",
        r"quale\s+(?:vino|bottiglia)\s+ho\s+pagato\s+di\s+pi[ùu]",
        r"(?:prezzo|costo)\s+acquisto\s+(?:pi[ùu]\s+)?alto",
    ]
    
    # Pattern per prezzo acquisto (min)
    min_cost_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?economic[oa]\s+(?:da\s+)?acquist[oa]",
        r"quale\s+(?:vino|bottiglia)\s+ho\s+pagato\s+di\s+meno",
        r"(?:prezzo|costo)\s+acquisto\s+(?:pi[ùu]\s+)?basso",
    ]
    
    # Pattern per annata (max - più recente)
    max_vintage_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?recente",
        r"quale\s+(?:vino|bottiglia)\s+(?:ha|con)\s+(?:annata|anno)\s+(?:pi[ùu]\s+)?recente",
        r"(?:annata|anno)\s+(?:pi[ùu]\s+)?recente",
    ]
    
    # Pattern per annata (min - più vecchio)
    min_vintage_patterns = [
        r"quale\s+(?:vino|bottiglia)\s+(?:è|è\s+il)\s+(?:pi[ùu]\s+)?vecchi[oa]",
        r"quale\s+(?:vino|bottiglia)\s+(?:ha|con)\s+(?:annata|anno)\s+(?:pi[ùu]\s+)?vecchi[oa]",
        r"(?:annata|anno)\s+(?:pi[ùu]\s+)?vecchi[oa]",
    ]
    
    # Controlla pattern
    if any(re.search(pt, p) for pt in min_quantity_patterns):
        return ('min', 'quantity')
    if any(re.search(pt, p) for pt in max_quantity_patterns):
        return ('max', 'quantity')
    if any(re.search(pt, p) for pt in max_price_patterns):
        return ('max', 'selling_price')
    if any(re.search(pt, p) for pt in min_price_patterns):
        return ('min', 'selling_price')
    if any(re.search(pt, p) for pt in max_cost_patterns):
        return ('max', 'cost_price')
    if any(re.search(pt, p) for pt in min_cost_patterns):
        return ('min', 'cost_price')
    if any(re.search(pt, p) for pt in max_vintage_patterns):
        return ('max', 'vintage')
    if any(re.search(pt, p) for pt in min_vintage_patterns):
        return ('min', 'vintage')
    
    return (None, None)


async def _handle_qualitative_query_fallback(telegram_id: int, prompt: str) -> Optional[str]:
    """
    Tenta di interpretare una query qualitativa quando l'AI non ha trovato una funzione diretta.
    Gestisce domande soggettive come "più pregiato", "migliore", "di valore", ecc.
    
    Args:
        telegram_id: ID Telegram utente
        prompt: Testo della query originale
    
    Returns:
        Risposta formattata o None se non riesce a interpretare
    """
    try:
        prompt_lower = prompt.lower().strip()
        
        # Mappa di pattern qualitativi a query_type e field
        qualitative_patterns = [
            # Pregiato/Valore/Prestigio → max selling_price
            (r'\b(più\s+)?pregiat[oi]|(di\s+)?valore|prestigio|miglior[ei]|qualità|più\s+costos[oi]|più\s+cara', 'max', 'selling_price'),
            # Economico → min selling_price
            (r'(più\s+)?economic[oi]|più\s+baratt[aio]|meno\s+costos[oi]|meno\s+cara', 'min', 'selling_price'),
            # Più bottiglie/quantità → max quantity
            (r'(più|maggiore)\s+(bottiglie|quantità|pezzi)|più\s+bottiglie', 'max', 'quantity'),
            # Meno bottiglie → min quantity
            (r'(meno|minore)\s+(bottiglie|quantità|pezzi)', 'min', 'quantity'),
            # Più pagato/costo acquisto → max cost_price
            (r'più\s+pagat[oi]|costo\s+(più|maggiore)|speso\s+(più|di\s+più)', 'max', 'cost_price'),
            # Meno pagato → min cost_price
            (r'meno\s+pagat[oi]|costo\s+(meno|minore)', 'min', 'cost_price'),
            # Più recente/nuovo → max vintage
            (r'più\s+(recente|nuov[oi]|giovane)', 'max', 'vintage'),
            # Più vecchio/antico → min vintage
            (r'più\s+(vecchi[oi]|antich[oi]|anzian[oi])', 'min', 'vintage'),
        ]
        
        # Cerca pattern nella query
        for pattern, query_type, field in qualitative_patterns:
            if re.search(pattern, prompt_lower):
                logger.info(f"[QUALITATIVE_FALLBACK] Pattern trovato: '{pattern}' → {query_type} {field}")
                # Usa la funzione esistente per gestire la query
                result = await _handle_informational_query(telegram_id, query_type, field)
                if result:
                    return result
        
        # Prova pattern sensoriali (tannico, corposo, floreale, ecc.)
        sensory_result = await _handle_sensory_query(telegram_id, prompt)
        if sensory_result:
            return sensory_result
        
        # Se non trova pattern, ritorna None (usa risposta AI originale)
        return None
        
    except Exception as e:
        logger.error(f"Errore in _handle_qualitative_query_fallback: {e}", exc_info=True)
        return None


async def _retry_level_1_normalize_local(query: str) -> list[str]:
    """
    Livello 1: Normalizzazione locale (plurali, accenti).
    Genera varianti normalizzate del termine di ricerca.
    
    Returns:
        Lista di varianti da provare (originale + normalizzate)
    """
    variants = [query]
    query_lower = query.lower().strip()
    
    # Normalizzazione plurali (stessa logica di search_wines)
    if len(query_lower) > 2:
        if query_lower.endswith('i'):
            # Plurale maschile: "vermentini" -> "vermentino"
            base = query_lower[:-1]
            variants.append(base + 'o')  # vermentino
            variants.append(base)  # vermentin
        elif query_lower.endswith('e'):
            # Plurale femminile: "bianche" -> "bianco"
            base = query_lower[:-1]
            variants.append(base + 'a')  # bianca
            variants.append(base + 'o')  # bianco
            variants.append(base)  # bianch
    
    # Rimuovi accenti/apostrofi (normalizzazione base)
    # Nota: search_wines gestisce già accenti, ma aggiungiamo varianti senza apostrofi
    if "'" in query:
        variants.append(query.replace("'", ""))
    if "'" in query:  # apostrofo unicode (diverso carattere)
        variants.append(query.replace("'", ""))
    
    return list(set(variants))  # Rimuovi duplicati mantenendo ordine


async def _retry_level_2_fallback_less_specific(
    telegram_id: int,
    original_filters: Dict[str, Any],
    original_query: Optional[str] = None
) -> Optional[List]:
    """
    Livello 2: Fallback a ricerca meno specifica.
    Rimuove filtri troppo specifici e prova ricerca generica.
    
    Returns:
        Lista di vini trovati o None se fallimento
    """
    try:
        from .database_async import async_db_manager
        
        # Estrai termini chiave dai filtri per ricerca generica
        fallback_queries = []
        
        # Se c'è producer, usa come query generica
        if "producer" in original_filters and original_filters["producer"]:
            fallback_queries.append(original_filters["producer"])
        
        # Se c'è name_contains, usa come query generica
        if "name_contains" in original_filters and original_filters["name_contains"]:
            fallback_queries.append(original_filters["name_contains"])
        
        # Se c'è una query originale, usala
        if original_query:
            fallback_queries.append(original_query)
        
        # Prova ogni query fallback con search_wines (ricerca generica)
        for fallback_query in fallback_queries:
            if not fallback_query or not fallback_query.strip():
                continue
            
            logger.info(f"[RETRY_L2] Provo ricerca meno specifica con: '{fallback_query}'")
            wines = await async_db_manager.search_wines(telegram_id, fallback_query.strip(), limit=50)
            if wines:
                logger.info(f"[RETRY_L2] ✅ Trovati {len(wines)} vini con ricerca meno specifica")
                return wines
        
        return None
    except Exception as e:
        logger.error(f"[RETRY_L2] Errore in fallback meno specifica: {e}", exc_info=True)
        return None


async def _retry_level_3_ai_post_processing(
    original_query: str,
    failed_search_term: Optional[str] = None,
    original_filters: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Livello 3: AI Post-Processing.
    Chiama OpenAI per reinterpretare/suggerire query alternativa.
    
    Returns:
        Query alternativa suggerita dall'AI o None
    """
    try:
        from openai import OpenAI
        from .config import OPENAI_API_KEY, OPENAI_MODEL
        
        if not OPENAI_API_KEY:
            logger.warning("[RETRY_L3] OPENAI_API_KEY non disponibile, salto AI Post-Processing")
            return None
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Costruisci prompt per AI
        context_parts = []
        if failed_search_term:
            context_parts.append(f"L'utente ha cercato: '{failed_search_term}'")
        elif original_query:
            context_parts.append(f"L'utente ha cercato: '{original_query}'")
        
        if original_filters:
            filters_str = ", ".join([f"{k}: {v}" for k, v in original_filters.items() if v])
            if filters_str:
                context_parts.append(f"Filtri applicati: {filters_str}")
        
        context_parts.append("La ricerca nel database non ha trovato risultati.")
        
        retry_prompt = f"""
{chr(10).join(context_parts)}

Suggerisci una query di ricerca alternativa normalizzata. Considera:
- Normalizzazione plurali (es. "vermentini" → "vermentino")
- Rimozione filtri troppo specifici
- Termine chiave principale da cercare

Rispondi SOLO con il termine di ricerca suggerito, senza spiegazioni, senza virgolette, senza punteggiatura finale.
Esempio di risposta: vermentino
"""
        
        logger.info(f"[RETRY_L3] Chiamo AI per reinterpretare query: {original_query[:50]}")
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Sei un assistente che aiuta a normalizzare query di ricerca per vini. Rispondi solo con il termine normalizzato."},
                {"role": "user", "content": retry_prompt}
            ],
            max_tokens=50,
            temperature=0.3  # Bassa temperatura per risposte più deterministiche
        )
        
        if response.choices and response.choices[0].message.content:
            retry_query = response.choices[0].message.content.strip().strip('"').strip("'").strip()
            if retry_query and retry_query != original_query and len(retry_query) > 1:
                logger.info(f"[RETRY_L3] ✅ AI suggerisce query alternativa: '{retry_query}'")
                return retry_query
        
        return None
    except Exception as e:
        logger.error(f"[RETRY_L3] Errore in AI Post-Processing: {e}", exc_info=True)
        return None


async def _cascading_retry_search(
    telegram_id: int,
    original_query: str,
    search_func,
    search_func_args: Dict[str, Any],
    original_filters: Optional[Dict[str, Any]] = None
) -> tuple[Optional[List], Optional[str], str]:
    """
    Esegue ricerca con cascata di retry a 3 livelli.
    
    Args:
        telegram_id: ID Telegram utente
        original_query: Query originale dell'utente
        search_func: Funzione di ricerca da chiamare (es. async_db_manager.search_wines)
        search_func_args: Argomenti per search_func
        original_filters: Filtri originali (se ricerca filtrata)
    
    Returns:
        (wines_found, retry_query_used, level_used)
        wines_found: Lista vini trovati o None
        retry_query_used: Query usata nel retry (se applicabile)
        level_used: "original", "level1", "level2", "level3", "failed"
    """
    from .database_async import async_db_manager
    
    # Tentativo originale
    try:
        wines = await search_func(**search_func_args)
        if wines:
            logger.info(f"[RETRY] ✅ Ricerca originale ha trovato {len(wines)} vini")
            return wines, None, "original"
    except Exception as e:
        logger.warning(f"[RETRY] Errore ricerca originale: {e}")
    
    # Livello 1: Normalizzazione locale (solo per ricerca non filtrata o con name_contains)
    # Per ricerca filtrata con producer/region, passa direttamente a Livello 2
    if not original_filters or "name_contains" in search_func_args.get("filters", {}):
        variants = await _retry_level_1_normalize_local(original_query)
        for variant in variants[1:]:  # Skip primo (originale già provato)
            if variant == original_query:
                continue
            try:
                # Prova con variante normalizzata
                args_retry = search_func_args.copy()
                if "search_term" in args_retry:
                    args_retry["search_term"] = variant
                elif "query" in args_retry:
                    args_retry["query"] = variant
                elif "filters" in args_retry:
                    # Per search_wines_filtered, aggiungi variant come name_contains
                    args_retry["filters"] = args_retry["filters"].copy()
                    args_retry["filters"]["name_contains"] = variant
                
                wines = await search_func(**args_retry)
                if wines:
                    logger.info(f"[RETRY_L1] ✅ Trovati {len(wines)} vini con variante normalizzata: '{variant}'")
                    return wines, variant, "level1"
            except Exception as e:
                logger.debug(f"[RETRY_L1] Variante '{variant}' fallita: {e}")
                continue
    
    # Livello 2: Fallback a ricerca meno specifica (solo se ricerca filtrata)
    if original_filters:
        logger.info(f"[RETRY_L2] Avvio fallback ricerca meno specifica per query filtrata: '{original_query}'")
        wines = await _retry_level_2_fallback_less_specific(
            telegram_id, original_filters, original_query
        )
        if wines:
            logger.info(f"[RETRY_L2] ✅ Fallback riuscito: trovati {len(wines)} vini")
            return wines, None, "level2"
        else:
            logger.info(f"[RETRY_L2] ❌ Fallback non ha trovato risultati")
    
    # Livello 3: AI Post-Processing
    logger.info(f"[RETRY_L3] Avvio AI Post-Processing per: '{original_query}'")
    retry_query = await _retry_level_3_ai_post_processing(
        original_query, original_query, original_filters
    )
    if retry_query:
        logger.info(f"[RETRY_L3] Query suggerita da AI: '{retry_query}'")
        try:
            # Per ricerca filtrata, usa sempre search_wines generico con query AI
            # Per ricerca semplice, prova con search_func modificato
            if original_filters:
                # Ricerca filtrata: usa search_wines generico
                wines = await async_db_manager.search_wines(telegram_id, retry_query, limit=50)
                if wines:
                    logger.info(f"[RETRY_L3] ✅ Trovati {len(wines)} vini con query AI (ricerca generica): '{retry_query}'")
                    return wines, retry_query, "level3"
            else:
                # Ricerca semplice: prova con search_func modificato
                args_retry = search_func_args.copy()
                if "search_term" in args_retry:
                    args_retry["search_term"] = retry_query
                elif "query" in args_retry:
                    args_retry["query"] = retry_query
                
                wines = await search_func(**args_retry)
                if wines:
                    logger.info(f"[RETRY_L3] ✅ Trovati {len(wines)} vini con query AI: '{retry_query}'")
                    return wines, retry_query, "level3"
        except Exception as e:
            logger.warning(f"[RETRY_L3] Errore ricerca con query AI: {e}", exc_info=True)
    
    logger.warning(f"[RETRY] ❌ TUTTI I LIVELLI DI RETRY FALLITI per query: '{original_query}' (livelli provati: originale → L1 → L2 → L3)")
    return None, None, "failed"


async def _handle_sensory_query(telegram_id: int, prompt: str) -> Optional[str]:
    """
    Gestisce query sensoriali usando approccio ibrido:
    1. Ricerca parole chiave in description/notes
    2. Mappatura euristica (wine_type + alcohol_content)
    3. Mappatura per uvaggi tipici
    4. Combina e ordina risultati
    
    Args:
        telegram_id: ID Telegram utente
        prompt: Testo della query originale
    
    Returns:
        Risposta formattata o None se non riesce a interpretare
    """
    try:
        prompt_lower = prompt.lower().strip()
        from .database_async import async_db_manager, get_async_session
        from sqlalchemy import text as sql_text
        from .response_templates import format_wine_info
        
        # Mappatura caratteristiche sensoriali
        sensory_mapping = {
            'tannico': {
                'keywords': ['tannico', 'tannini', 'strutturato', 'tanninico', 'astringente'],
                'wine_types': ['Rosso'],  # I vini tannici sono tipicamente rossi
                'grape_varieties': ['Nebbiolo', 'Cabernet', 'Sangiovese', 'Montepulciano', 'Cabernet Sauvignon', 'Aglianico', 'Tannat'],
                'order_by': 'alcohol_content DESC',  # Proxy per struttura
                'description': 'tannici'
            },
            'corposo': {
                'keywords': ['corposo', 'corpo', 'strutturato', 'denso', 'ricco'],
                'wine_types': None,  # Può essere rosso o bianco
                'grape_varieties': ['Chardonnay', 'Amarone', 'Barolo', 'Brunello', 'Montepulciano', 'Nebbiolo'],
                'order_by': 'alcohol_content DESC',  # Gradazione alta = più corpo
                'description': 'corposi'
            },
            'floreale': {
                'keywords': ['floreale', 'fiore', 'fiorito', 'profumato', 'aromatico'],
                'wine_types': ['Bianco', 'Rosato'],  # Tipicamente bianchi/rosati
                'grape_varieties': ['Sauvignon', 'Gewürztraminer', 'Gewurtzraminer', 'Moscato', 'Riesling', 'Malvasia', 'Traminer'],
                'order_by': None,  # Non correlato a gradazione
                'description': 'floreali'
            },
            'secco': {
                'keywords': ['secco', 'asciutto', 'non dolce'],
                'wine_types': None,  # Può essere qualsiasi tipo
                'grape_varieties': None,  # Non specifico per uvaggio
                'order_by': 'alcohol_content DESC',  # Vini secchi spesso più alcolici
                'description': 'secchi'
            },
            'boccato': {
                'keywords': ['boccato', 'bocca', 'persistente', 'lungo', 'concentrato'],
                'wine_types': None,
                'grape_varieties': ['Nebbiolo', 'Sangiovese', 'Cabernet', 'Aglianico'],
                'order_by': 'alcohol_content DESC',  # Gradazione alta = più persistenza
                'description': 'boccati'
            }
        }
        
        # Identifica caratteristica sensoriale richiesta
        matched_sensory = None
        for sensory_key, config in sensory_mapping.items():
            # Pattern per "vino più [caratteristica]"
            pattern = rf'\b(più\s+)?{sensory_key}\b|\b{config["description"]}\b'
            if re.search(pattern, prompt_lower):
                matched_sensory = sensory_key
                break
        
        if not matched_sensory:
            return None
        
        logger.info(f"[SENSORY_QUERY] Caratteristica rilevata: {matched_sensory}")
        config = sensory_mapping[matched_sensory]
        
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name:
            return None
        
        table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
        all_results = []  # Lista di tuple (wine, score)
        
        async with await get_async_session() as session:
            # 1. RICERCA NEI CAMPI TESTUALI (priorità alta)
            if config['keywords']:
                keyword_conditions = []
                params = {"user_id": user.id}
                for idx, keyword in enumerate(config['keywords']):
                    keyword_conditions.append(f"(LOWER(description) LIKE :kw_{idx} OR LOWER(notes) LIKE :kw_{idx})")
                    params[f"kw_{idx}"] = f"%{keyword}%"
                
                if keyword_conditions:
                    keyword_query = sql_text(f"""
                        SELECT *
                        FROM {table_name}
                        WHERE user_id = :user_id
                        AND ({' OR '.join(keyword_conditions)})
                        LIMIT 50
                    """)
                    result = await session.execute(keyword_query, params)
                    rows = result.fetchall()
                    
                    for row in rows:
                        wine = _row_to_wine(row)
                        if wine:
                            all_results.append((wine, 10))  # Score alto per match diretto
            
            # 2. MAPPATURA EURISTICA (wine_type + alcohol_content)
            if config['wine_types'] or config['order_by']:
                euristic_filters = []
                euristic_params = {"user_id": user.id}
                
                if config['wine_types']:
                    wine_type_conditions = []
                    for idx, wt in enumerate(config['wine_types']):
                        wine_type_conditions.append(f"wine_type = :wt_{idx}")
                        euristic_params[f"wt_{idx}"] = wt
                    euristic_filters.append(f"({' OR '.join(wine_type_conditions)})")
                
                if config['order_by']:
                    order_clause = f"ORDER BY {config['order_by']} NULLS LAST"
                else:
                    order_clause = "ORDER BY name ASC"
                
                euristic_query = sql_text(f"""
                    SELECT *
                    FROM {table_name}
                    WHERE user_id = :user_id
                    {'AND ' + ' AND '.join(euristic_filters) if euristic_filters else ''}
                    {order_clause}
                    LIMIT 30
                """)
                
                result = await session.execute(euristic_query, euristic_params)
                rows = result.fetchall()
                
                for row in rows:
                    wine = _row_to_wine(row)
                    if wine and not any(w.id == wine.id for w, _ in all_results):
                        score = 7 if config['wine_types'] else 5  # Score medio-alto
                        all_results.append((wine, score))
            
            # 3. MAPPATURA PER UVAGGI TIPICI
            if config['grape_varieties']:
                grape_conditions = []
                grape_params = {"user_id": user.id}
                for idx, grape in enumerate(config['grape_varieties']):
                    grape_conditions.append(f"LOWER(grape_variety) LIKE :grape_{idx}")
                    grape_params[f"grape_{idx}"] = f"%{grape.lower()}%"
                
                if grape_conditions:
                    grape_query = sql_text(f"""
                        SELECT *
                        FROM {table_name}
                        WHERE user_id = :user_id
                        AND ({' OR '.join(grape_conditions)})
                        ORDER BY alcohol_content DESC NULLS LAST
                        LIMIT 30
                    """)
                    result = await session.execute(grape_query, grape_params)
                    rows = result.fetchall()
                    
                    for row in rows:
                        wine = _row_to_wine(row)
                        if wine and not any(w.id == wine.id for w, _ in all_results):
                            all_results.append((wine, 6))  # Score medio
            
            # 4. ORDINA PER SCORE (priorità) e rimuovi duplicati
            seen_ids = set()
            unique_results = []
            for wine, score in sorted(all_results, key=lambda x: x[1], reverse=True):
                if wine.id not in seen_ids:
                    seen_ids.add(wine.id)
                    unique_results.append(wine)
                    if len(unique_results) >= 10:  # Max 10 risultati
                        break
            
            if not unique_results:
                return f"❌ Non ho trovato vini {config['description']} nel tuo inventario. 💡 Prova ad aggiungere descrizioni dettagliate ai tuoi vini per ottenere risultati migliori."
            
            # 5. FORMATTA RISPOSTA COLLOQUIALE usando format_wines_response_by_count
            query_context = f"più {config['description']}"
            return await format_wines_response_by_count(unique_results, telegram_id, query_context)
        
    except Exception as e:
        logger.error(f"Errore in _handle_sensory_query: {e}", exc_info=True)
        return None


def _row_to_wine(row) -> Optional[Any]:
    """Converte una riga SQL in oggetto Wine"""
    try:
        from .database_async import Wine
        wine = Wine()
        for key in ['id', 'user_id', 'name', 'producer', 'vintage', 'grape_variety',
                   'region', 'country', 'wine_type', 'classification', 'quantity',
                   'min_quantity', 'cost_price', 'selling_price', 'alcohol_content',
                   'description', 'notes', 'created_at', 'updated_at']:
            if hasattr(row, key):
                setattr(wine, key, getattr(row, key))
        return wine
    except Exception as e:
        logger.error(f"Errore conversione row to wine: {e}")
        return None


async def _handle_informational_query(telegram_id: int, query_type: str, field: str) -> Optional[str]:
    """
    Gestisce una domanda informativa generica e ritorna la risposta formattata.
    
    Args:
        telegram_id: ID Telegram utente
        query_type: 'min' o 'max'
        field: Campo da interrogare ('quantity', 'selling_price', 'cost_price', 'vintage')
    
    Returns:
        Risposta formattata o None se errore
    """
    try:
        from .database_async import async_db_manager
        from .response_templates import format_wine_info
        
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name:
            return None
        
        table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
        
        # Determina ORDER BY e NULLS LAST/FIRST
        if query_type == 'max':
            order_by = f"{field} DESC NULLS LAST"
            if field == 'vintage':
                # Per vintage, NULL va alla fine (vini senza annata)
                order_by = f"{field} DESC NULLS LAST"
        else:  # min
            order_by = f"{field} ASC NULLS LAST"
            if field == 'vintage':
                # Per vintage, NULL va alla fine (vini senza annata)
                order_by = f"{field} ASC NULLS LAST"
        
        # Query SQL: prima trova il valore min/max, poi tutti i vini con quel valore
        from sqlalchemy import text as sql_text
        from .database_async import get_async_session
        
        # Step 1: Trova il valore min/max
        find_value_query = sql_text(f"""
            SELECT {field}
            FROM {table_name}
            WHERE user_id = :user_id
            AND {field} IS NOT NULL
            ORDER BY {order_by}
            LIMIT 1
        """)
        
        async with await get_async_session() as session:
            result = await session.execute(find_value_query, {"user_id": user.id})
            value_row = result.fetchone()
            
            if not value_row:
                # Nessun vino trovato con quel campo valorizzato
                field_names = {
                    'quantity': 'quantità',
                    'selling_price': 'prezzo di vendita',
                    'cost_price': 'prezzo di acquisto',
                    'vintage': 'annata'
                }
                field_name = field_names.get(field, field)
                return f"❌ Non ho trovato vini con {field_name} specificato nel tuo inventario."
            
            target_value = value_row[0]
            
            # Step 2: Trova TUTTI i vini con quel valore
            find_all_query = sql_text(f"""
                SELECT *
                FROM {table_name}
                WHERE user_id = :user_id
                AND {field} = :target_value
                ORDER BY name ASC
                LIMIT 20
            """)
            
            result = await session.execute(find_all_query, {"user_id": user.id, "target_value": target_value})
            rows = result.fetchall()
            
            if not rows:
                return f"❌ Errore: valore trovato ma nessun vino corrispondente."
            
            # Costruisci oggetti Wine
            from .database_async import Wine
            wines = []
            for row in rows:
                wine_dict = {
                    'id': row.id,
                    'user_id': row.user_id,
                    'name': row.name,
                    'producer': row.producer,
                    'vintage': row.vintage,
                    'grape_variety': row.grape_variety,
                    'region': row.region,
                    'country': row.country,
                    'wine_type': row.wine_type,
                    'classification': row.classification,
                    'quantity': row.quantity,
                    'min_quantity': row.min_quantity if hasattr(row, 'min_quantity') else 0,
                    'cost_price': row.cost_price,
                    'selling_price': row.selling_price,
                    'alcohol_content': row.alcohol_content,
                    'description': row.description,
                    'notes': row.notes,
                    'created_at': row.created_at,
                    'updated_at': row.updated_at
                }
                
                wine = Wine()
                for key, value in wine_dict.items():
                    setattr(wine, key, value)
                wines.append(wine)
            
            # Aggiungi contesto alla risposta
            field_names = {
                'quantity': 'quantità',
                'selling_price': 'prezzo di vendita',
                'cost_price': 'prezzo di acquisto',
                'vintage': 'annata'
            }
            query_names = {
                'min': {'quantity': 'minore quantità', 'selling_price': 'prezzo più basso', 
                       'cost_price': 'costo acquisto più basso', 'vintage': 'annata più vecchia'},
                'max': {'quantity': 'maggiore quantità', 'selling_price': 'prezzo più alto',
                       'cost_price': 'costo acquisto più alto', 'vintage': 'annata più recente'}
            }
            
            query_desc = query_names.get(query_type, {}).get(field, field)
            
            # Usa format_wines_response_by_count per gestire i 3 casi
            query_context = f"con {query_desc}"
            return await format_wines_response_by_count(wines, telegram_id, query_context)
            
    except Exception as e:
        logger.error(f"[INFORMATIONAL_QUERY] Errore gestione query informativa: {e}", exc_info=True)
        return None


async def format_wines_response_by_count(wines: list, telegram_id: int = None, query_context: str = "") -> str:
    """
    Formatta risposta in base al numero di vini trovati:
    - 1 vino: info message completo
    - 2-10 vini: sommario + pulsanti selezione
    - >10 vini: messaggio informativo + link al viewer
    
    Args:
        wines: Lista di vini trovati
        telegram_id: ID Telegram per generare link viewer (opzionale, richiesto se >10 vini)
        query_context: Contesto opzionale per personalizzare il messaggio (es. "più tannici")
    
    Returns:
        Stringa formattata con marker appropriati
    """
    if not wines:
        from .response_templates import format_search_no_results
        return format_search_no_results({})
    
    num_wines = len(wines)
    
    # Caso 1: 1 solo vino → info message completo
    if num_wines == 1:
        return format_wine_info(wines[0])
    
    # Caso 2: 2-10 vini → sommario + pulsanti selezione
    if 2 <= num_wines <= 10:
        summary = format_inventory_list(wines, limit=num_wines)
        wine_ids = [str(w.id) for w in wines[:10]]
        buttons_marker = f"[[WINE_SELECTION_BUTTONS:{':'.join(wine_ids)}]]"
        return summary + "\n\n" + buttons_marker
    
    # Caso 3: >10 vini → messaggio informativo + link al viewer
    if num_wines > 10:
        # Genera link al viewer se telegram_id disponibile
        viewer_link_text = ""
        if telegram_id:
            try:
                from .viewer_utils import generate_viewer_token, get_viewer_url
                
                user = await async_db_manager.get_user_by_telegram_id(telegram_id)
                if user and user.business_name:
                    token = generate_viewer_token(telegram_id, user.business_name)
                    if token:
                        viewer_url = get_viewer_url(token)
                        viewer_link_text = f"\n\n🔗 [Clicca qui per vedere tutto l'inventario]({viewer_url})"
            except Exception as e:
                logger.warning(f"Errore generazione link viewer: {e}")
        
        if query_context:
            context_text = f" {query_context}"
        else:
            context_text = " che corrispondono alla tua ricerca"
        
        return (
            f"🍷 **Hai tanti vini{context_text}!**\n\n"
            f"Ho trovato **{num_wines} vini**.\n\n"
            f"💡 Per vedere tutti i vini e filtrare facilmente, clicca sul link qui sotto:{viewer_link_text}"
        )
    
    # Fallback: usa format_inventory_list normale
    return format_inventory_list(wines, limit=50)


async def _build_inventory_list_response(telegram_id: int, limit: int = 50) -> str:
    """Recupera l'inventario utente e lo formatta usando template pre-strutturato."""
    try:
        wines = await async_db_manager.get_user_wines(telegram_id)
        return format_inventory_list(wines, limit=limit)
    except Exception as e:
        logger.error(f"Errore creazione lista inventario: {e}")
        return "⚠️ Errore nel recupero dell'inventario. Riprova con /view."


def _parse_filters(prompt: str) -> dict:
    """Estrae filtri semplici dal linguaggio naturale (regioni, tipo, prezzo, annata, produttore, paese)."""
    p = prompt.lower()
    filters = {}
    
    # Paese (deve essere prima delle regioni per evitare conflitti)
    # ✅ Sinonimi estesi per country
    if re.search(r'\b(itali[ae]?|italy)\b', p):
        filters['country'] = 'Italia'
    if re.search(r'\b(frances[ei]?|france)\b', p):
        filters['country'] = 'Francia'
    if re.search(r'\b(spagnol[oi]?|spain)\b', p):
        filters['country'] = 'Spagna'
    if re.search(r'\b(tedes[ch]?[hi]?|germany)\b', p):
        filters['country'] = 'Germania'
    if re.search(r'\b(stati\s+uniti|stati\s+uniti\s+d[\'"]?america|america|united\s+states|us)\b', p):
        filters['country'] = 'USA'
    if re.search(r'\b(portoghes[ei]?|portugal)\b', p):
        filters['country'] = 'Portogallo'
    if re.search(r'\b(australian[oi]?|australia)\b', p):
        filters['country'] = 'Australia'
    if re.search(r'\b(cilen[oi]?|chile)\b', p):
        filters['country'] = 'Cile'
    if re.search(r'\b(argentin[oi]?|argentina)\b', p):
        filters['country'] = 'Argentina'
    
    # Regioni (solo se non c'è già un filtro paese o se è Italia)
    regions = [
        'toscana','toscata',  # Fix: "toscata" → "Toscana"
        'piemonte','veneto','sicilia','sardegna','lombardia','marche','umbria','lazio',
        'puglia','abruzzo','friuli','trentino','alto adige','campania','liguria','emilia','romagna'
    ]
    for r in regions:
        if r in p:
            # Normalizza variazioni
            if r == 'toscata':
                filters['region'] = 'Toscana'
            elif r == 'alto adige':
                filters['region'] = 'Alto Adige'
            else:
                filters['region'] = r.capitalize()
            break
    if re.search(r'\brossi?\b', p):
        filters['wine_type'] = 'rosso'
    if re.search(r'\bbianc[oi]\b', p):
        filters['wine_type'] = 'bianco'
    if 'spumante' in p:
        filters['wine_type'] = 'spumante'
    if 'rosato' in p:
        filters['wine_type'] = 'rosato'
    m = re.search(r'prezzo\s*(sotto|inferiore|<)\s*€?\s*(\d+[\.,]?\d*)', p)
    if m:
        filters['price_max'] = float(m.group(2).replace(',', '.'))
    m = re.search(r'prezzo\s*(sopra|maggiore|>)\s*€?\s*(\d+[\.,]?\d*)', p)
    if m:
        filters['price_min'] = float(m.group(2).replace(',', '.'))
    m = re.search(r'(?:dal|da)\s*((?:19|20)\d{2})', p)
    if m:
        filters['vintage_min'] = int(m.group(1))
    m = re.search(r'(?:fino\s*al|al)\s*((?:19|20)\d{2})', p)
    if m:
        filters['vintage_max'] = int(m.group(1))
    m = re.search(r"produttore\s+([\w\s'’]+)", p)
    if m:
        filters['producer'] = m.group(1).strip()
    return filters

async def _check_movement_with_ai(prompt: str, telegram_id: int) -> str:
    """
    Usa OpenAI per rilevare se il messaggio è un movimento inventario quando regex non match.
    Gestisce variazioni linguistiche naturali come "mi sono arrivati", "arrivati", ecc.
    """
    try:
        import json
        import openai
        
        # Usa le variabili già definite nel modulo
        if not OPENAI_API_KEY:
            return None
        
        # Verifica condizioni base (stesse del check regex) - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name or user.business_name == "Upload Manuale":
            return None
        
        user_wines = await async_db_manager.get_user_wines(telegram_id)
        if not user_wines or len(user_wines) == 0:
            return None
        
        # Prompt specifico per rilevare movimenti
        movement_detection_prompt = f"""Analizza questo messaggio e determina se indica un movimento inventario (consumo o rifornimento di vini).

MESSAGGIO: "{prompt}"

Un movimento può essere espresso in molti modi:
- Rifornimento: "mi sono arrivati X vini", "arrivati X", "sono arrivati X", "ho ricevuto X", "comprato X", "ho acquistato X", ecc.
- Consumo: "ho venduto X", "ho consumato X", "ho bevuto X", "venduto X", ecc.

IMPORTANTE: Se il messaggio contiene movimenti multipli (es. "ho acquistato 1 vino A e 1 vino B"), estrai solo il PRIMO movimento. 
I movimenti multipli vengono gestiti automaticamente dal sistema di parsing.

Rispondi SOLO con un JSON valido in questo formato (senza testo aggiuntivo):
{{
    "is_movement": true o false,
    "type": "consumo" o "rifornimento" o null,
    "quantity": numero intero o null,
    "wine_name": "nome del vino" o null
}}

Esempi:
- "mi sono arrivati 6 gavi" → {{"is_movement": true, "type": "rifornimento", "quantity": 6, "wine_name": "gavi"}}
- "ho consumato 5 sassicaia" → {{"is_movement": true, "type": "consumo", "quantity": 5, "wine_name": "sassicaia"}}
- "ho acquistato 1 hexenbicler e 1 unterebner" → {{"is_movement": true, "type": "rifornimento", "quantity": 1, "wine_name": "hexenbicler"}}
- "quanti vini ho?" → {{"is_movement": false, "type": null, "quantity": null, "wine_name": null}}
"""
        
        # Usa OPENAI_MODEL dal modulo (già importato)
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,  # Importato da .config all'inizio del file
            messages=[
                {"role": "system", "content": "Sei un analizzatore di messaggi. Rispondi SOLO con JSON valido, senza testo aggiuntivo."},
                {"role": "user", "content": movement_detection_prompt}
            ],
            max_tokens=150,
            temperature=0.1  # Bassa temperatura per risposte più deterministiche
        )
        
        if not response.choices or not response.choices[0].message.content:
            return None
        
        result_text = response.choices[0].message.content.strip()
        logger.info(f"[AI-MOVEMENT] Risposta AI rilevamento: {result_text}")
        
        # Estrai JSON dalla risposta (potrebbe essere in un code block)
        json_text = result_text
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(json_text)
        
        # ✅ VALIDAZIONE OUTPUT LLM con Pydantic (gestione graceful se modulo mancante)
        validated = None
        try:
            from .ai_validation import validate_movement_result
            validated = validate_movement_result(result)
        except ImportError:
            logger.warning("[AI-MOVEMENT] Modulo ai_validation non disponibile, uso validazione base")
            # Validazione base senza Pydantic
            if isinstance(result, dict) and result.get("is_movement") and result.get("type") and result.get("quantity") and result.get("wine_name"):
                validated = type('ValidatedResult', (), {
                    'is_movement': True,
                    'type': result.get("type"),
                    'quantity': result.get("quantity"),
                    'wine_name': result.get("wine_name")
                })()
        
        if validated and validated.is_movement and validated.type and validated.quantity and validated.wine_name:
            movement_type = validated.type
            quantity = validated.quantity
            wine_name = validated.wine_name.strip()
            logger.info(f"[AI-MOVEMENT] Movimento rilevato da AI (validated): {movement_type} {quantity} {wine_name}")
            return f"__MOVEMENT__:{movement_type}:{quantity}:{wine_name}"
        
        return None
        
    except json.JSONDecodeError as e:
        logger.error(f"[AI-MOVEMENT] Errore parsing JSON da AI: {e}, risposta: {result_text if 'result_text' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore chiamata AI per rilevamento movimento: {e}")
        return None


async def _check_and_process_movement(prompt: str, telegram_id: int) -> str:
    """
    Rileva se il prompt contiene un movimento inventario (consumo/rifornimento).
    Usa pattern centralizzati da movement_patterns.
    Se sì, lo processa direttamente e ritorna il messaggio di conferma.
    Se no, ritorna None e il flow continua normalmente con l'AI.
    """
    try:
        from .movement_patterns import parse_single_movement, CONSUMO_PATTERNS_SIMPLE, RIFORNIMENTO_PATTERNS_SIMPLE, parse_movement_pattern
        
        # Verifica se utente esiste e ha business_name valido + inventario - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            return None  # Utente non trovato
        
        # Verifica business_name valido (non null e non "Upload Manuale")
        if not user.business_name or user.business_name == "Upload Manuale":
            return None  # Business name non valido
        
        # Verifica che l'inventario abbia almeno 1 vino
        user_wines = await async_db_manager.get_user_wines(telegram_id)
        if not user_wines or len(user_wines) == 0:
            return None  # Inventario vuoto
        
        # Se onboarding non completato ma condizioni sono soddisfatte, completa automaticamente
        if not user.onboarding_completed:
            await async_db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                onboarding_completed=True
            )
            logger.info(f"[AI-MOVEMENT] Onboarding completato automaticamente per {telegram_id} (business_name={user.business_name}, {len(user_wines)} vini)")
        
        # Prova prima con pattern completi (supportano numeri in lettere)
        result = parse_single_movement(prompt)
        if result:
            movement_type, quantity, wine_name = result
            logger.info(f"[AI-MOVEMENT] Rilevato {movement_type} (pattern completo): {quantity} {wine_name}")
            return f"__MOVEMENT__:{movement_type}:{quantity}:{wine_name}"
        
        # Prova con pattern semplici (solo numeri interi) per compatibilità
        result = parse_movement_pattern(prompt, CONSUMO_PATTERNS_SIMPLE, allow_word_numbers=False)
        if result:
            quantity, wine_name = result
            logger.info(f"[AI-MOVEMENT] Rilevato consumo (pattern semplice): {quantity} {wine_name}")
            return f"__MOVEMENT__:consumo:{quantity}:{wine_name}"
        
        result = parse_movement_pattern(prompt, RIFORNIMENTO_PATTERNS_SIMPLE, allow_word_numbers=False)
        if result:
            quantity, wine_name = result
            logger.info(f"[AI-MOVEMENT] Rilevato rifornimento (pattern semplice): {quantity} {wine_name}")
            return f"__MOVEMENT__:rifornimento:{quantity}:{wine_name}"
        
        # Se regex non ha matchato, usa AI per rilevare movimenti con variazioni linguistiche
        logger.info(f"[AI-MOVEMENT] Regex non matchato, provo con AI per: {prompt[:50]}")
        ai_movement_result = await _check_movement_with_ai(prompt, telegram_id)
        if ai_movement_result:
            logger.info(f"[AI-MOVEMENT] Rilevato movimento tramite AI: {ai_movement_result}")
            return ai_movement_result
        
        return None  # Nessun movimento rilevato
        
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore rilevamento movimento: {e}")
        return None  # In caso di errore, passa all'AI normale


async def _process_movement_async(telegram_id: int, wine_name: str, movement_type: str, quantity: int) -> str:
    """
    Processa movimento in modo asincrono.
    Usato quando l'AI rileva un movimento direttamente dal prompt.
    Usa fuzzy matching centralizzato sempre attivo.
    """
    try:
        from .processor_client import processor_client
        from .movement_utils import fuzzy_match_wine_name, format_movement_error_message, format_movement_success_message
        
        # Recupera business_name - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name:
            return "❌ **Errore**: Nome locale non trovato.\nCompleta prima l'onboarding con `/start`."
        
        business_name = user.business_name
        
        # ✅ FUZZY MATCHING: Usa funzione centralizzata sempre attiva
        matching_wines = await fuzzy_match_wine_name(telegram_id, wine_name, limit=10)
        
        if matching_wines:
            # Se trova un solo match, usa quello (correzione typo automatica)
            if len(matching_wines) == 1:
                corrected_wine_name = matching_wines[0].name
                logger.info(
                    f"[AI-MOVEMENT] Fuzzy matching: '{wine_name}' → '{corrected_wine_name}' "
                    f"(match unico trovato)"
                )
                wine_name = corrected_wine_name
            # Se trova più match, usa il primo (più probabile)
            else:
                corrected_wine_name = matching_wines[0].name
                logger.info(
                    f"[AI-MOVEMENT] Fuzzy matching: '{wine_name}' → '{corrected_wine_name}' "
                    f"({len(matching_wines)} match trovati, uso il primo)"
                )
                wine_name = corrected_wine_name
        
        # Processa movimento
        result = await processor_client.process_movement(
            telegram_id=telegram_id,
            business_name=business_name,
            wine_name=wine_name,
            movement_type=movement_type,
            quantity=quantity
        )
        
        if result.get('status') == 'success':
            return format_movement_success_message(
                movement_type,
                result.get('wine_name', wine_name),
                quantity,
                result.get('quantity_before', 0),
                result.get('quantity_after', 0)
            )
        else:
            error_msg = result.get('error', 'Errore sconosciuto')
            return format_movement_error_message(wine_name, error_msg, quantity)
                
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore processamento movimento: {e}")
        return f"❌ **Errore durante il processamento**\n\nErrore: {str(e)[:200]}\n\nRiprova più tardi."


def _clean_wine_search_term(term: str) -> str:
    """
    Pulisce il termine di ricerca rimuovendo parole interrogative, articoli, congiunzioni, ecc.
    ma preserva quelle che fanno parte del nome del vino (es. "del" in "Ca del Bosco").
    
    Args:
        term: Termine di ricerca grezzo
    
    Returns:
        Termine pulito per la ricerca
    """
    if not term:
        return term
    
    term_lower = term.lower().strip()
    
    # Parole interrogative da rimuovere
    interrogative_words = {'che', 'quale', 'quali', 'quanto', 'quanti', 'quante', 'cosa', 'cos\'', 'cos', 
                          'chi', 'dove', 'come', 'perché', 'perche', 'perchè'}
    
    # Articoli da rimuovere
    articles = {'il', 'lo', 'la', 'gli', 'le', 'i', 'un', 'uno', 'una'}
    
    # Verbi comuni che indicano possesso/richiesta
    common_verbs = {'ho', 'hai', 'ha', 'abbiamo', 'avete', 'hanno', 'è', 'sono', 'c\'è', 'ci sono',
                    'vendo', 'vendi', 'vende', 'vendiamo', 'vendete', 'vendono'}
    
    # Varianti comuni/typo di "vino" da rimuovere (es. "vinio", "vini")
    wine_variants = {'vino', 'vinio', 'vini', 'vinii', 'vinno'}
    
    # Preposizioni articolate che POTREBBERO far parte del nome (es. "del" in "Ca del Bosco")
    # Queste vengono preservate se seguite da una parola
    articulated_prepositions = {'del', 'della', 'dello', 'dei', 'degli', 'delle', 
                                'dal', 'dalla', 'dallo', 'dai', 'dagli', 'dalle'}
    
    # Preposizioni semplici da rimuovere solo se all'inizio
    simple_prepositions = {'di', 'da', 'in', 'su', 'per', 'con', 'tra', 'fra'}
    
    words = term_lower.split()
    if not words:
        return term
    
    cleaned_words = []
    
    # Rimuovi parole all'inizio che sono interrogative, articoli o verbi
    start_idx = 0
    for i, word in enumerate(words):
        if word in interrogative_words or word in articles:
            start_idx = i + 1
            continue
        break
    
    # Processa le parole rimanenti
    i = start_idx
    while i < len(words):
        word = words[i]
        
        # Se è una preposizione articolata (es. "del", "della"), potrebbe far parte del nome
        if word in articulated_prepositions:
            # Se c'è almeno una parola dopo, probabilmente fa parte del nome (es. "Ca del Bosco")
            if i + 1 < len(words):
                cleaned_words.append(word)
                i += 1
                continue
        
        # Rimuovi verbi comuni
        if word in common_verbs:
            i += 1
            continue
        
        # Rimuovi varianti/typo di "vino" (es. "vinio", "vini")
        if word in wine_variants:
            i += 1
            continue
        
        # Rimuovi preposizioni semplici solo se sono all'inizio della parte pulita
        if not cleaned_words and word in simple_prepositions:
            i += 1
            continue
        
        # Aggiungi la parola
        cleaned_words.append(word)
        i += 1
    
    result = ' '.join(cleaned_words).strip()
    
    # Rimuovi anche eventuali segni di punteggiatura finali
    result = re.sub(r'[?.,;:!]+$', '', result).strip()
    
    return result if result else term  # Se rimane vuoto, ritorna il termine originale


def _format_wine_response_directly(prompt: str, telegram_id: int, found_wines: list) -> str:
    """
    Genera risposte pre-formattate colorate per domande specifiche sui vini.
    Bypassa AI per risposte immediate e ben formattate.
    """
    prompt_lower = prompt.lower().strip()
    
    # Pattern per "quanti/quante X ho"
    quantity_patterns = [
        r'quanti (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
        r'quante (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
        r'quanti bottiglie? di (.+?) (?:ho|hai|ci sono)',
        r'quante bottiglie? di (.+?) (?:ho|hai|ci sono)',
    ]
    
    # Pattern per "quanto vendo/vendi/costa X"
    price_patterns = [
        r'a quanto (?:vendo|vendi|costano|prezzo) (.+?)',
        r'quanto (?:costa|costano|vendo|vendi) (.+?)',
        r'prezzo (.+?)',
        r'prezzo di vendita (.+?)',
    ]
    
    # Pattern per "info/dettagli/tutto su X" (più generici per catturare anche "sul X")
    info_patterns = [
        r'dimmi (?:tutto|tutte|tutta) (?:su|del|dello|della|sul) (.+?)',
        r'(?:informazioni|dettagli|info) (?:su|del|dello|della|sul) (.+?)',
        r'cosa sai (?:su|del|dello|della|sul) (.+?)',
        r'sul (.+?)(?:\?|$)',  # Pattern per "sul barolo cannubi"
        r'su (.+?)(?:\?|$)',    # Pattern per "su barolo"
        r'sul (.+)',             # Fallback senza fine frase
        r'su (.+)',              # Fallback senza fine frase
    ]
    
    # Se non ci sono vini trovati, passa all'AI
    if not found_wines:
        return None  # Passa all'AI normale
    
    # Se ci sono più vini, mostra bottoni per selezione invece di limitarsi al primo
    if len(found_wines) > 1:
        # Pattern per "che X ho?" - mostra tutti i vini
        che_ho_patterns = [
            r'che\s+(.+?)\s+ho\??',
            r'che\s+(.+?)\s+hai\??',
            r'quali\s+(.+?)\s+ho\??',
            r'quali\s+(.+?)\s+hai\??',
        ]
        for pattern in che_ho_patterns:
            if re.search(pattern, prompt_lower):
                logger.info(f"[FORMATTED] Pattern 'che X ho' rilevato con {len(found_wines)} vini, mostro bottoni")
                wine_ids = [str(w.id) for w in found_wines[:10]]  # Max 10 bottoni
                return f"[[WINE_SELECTION_BUTTONS:{':'.join(wine_ids)}]]"
        
        # Per altri pattern con più vini, mostra comunque bottoni per selezione
        logger.info(f"[FORMATTED] Trovati {len(found_wines)} vini, mostro bottoni per selezione invece di limitare al primo")
        wine_ids = [str(w.id) for w in found_wines[:10]]  # Max 10 bottoni
        return f"[[WINE_SELECTION_BUTTONS:{':'.join(wine_ids)}]]"
    
    wine = found_wines[0]  # Prendi il primo vino (più rilevante) - solo se c'è un solo vino
    
    # Controlla pattern "quanti X ho"
    for pattern in quantity_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_quantity(wine)
    
    # Controlla pattern "quanto vendo X"
    for pattern in price_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_price(wine)
    
    # Controlla pattern "info/dettagli su X"
    for pattern in info_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_info(wine)
    
    # Pattern per "X c'è?", "hai X?", "ce l'ho X?"
    exists_patterns = [
        r'(.+?)\s+c\'è\??',
        r'hai\s+(.+)',
        r'ce\s+l\'ho\s+(.+)',
        r'(.+?)\s+(?:è|ci sono|ce l\'hai)',
    ]
    for pattern in exists_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_exists(wine)
    
    # Pattern per "che X ho?" - se c'è un solo vino, mostra info
    che_ho_patterns = [
        r'che\s+(.+?)\s+ho\??',
        r'che\s+(.+?)\s+hai\??',
        r'quali\s+(.+?)\s+ho\??',
        r'quali\s+(.+?)\s+hai\??',
    ]
    for pattern in che_ho_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_info(wine)
    
    # Fallback: se il prompt contiene "su" o "sul" e abbiamo un vino, usa sempre format_wine_info
    if re.search(r'\b(su|sul)\b', prompt_lower) and wine:
        logger.info(f"[FORMATTED] Fallback: usando format_wine_info per prompt '{prompt_lower[:50]}'")
        return format_wine_info(wine)
    
    # Se nessun pattern match, passa all'AI
    return None


async def get_ai_response(prompt: str, telegram_id: int = None, correlation_id: str = None) -> str:
    """Genera risposta AI con accesso ai dati utente."""
    logger.info(f"=== DEBUG OPENAI ===")
    logger.info(f"OPENAI_API_KEY presente: {bool(OPENAI_API_KEY)}")
    logger.info(f"OPENAI_API_KEY valore: {OPENAI_API_KEY[:10] if OPENAI_API_KEY else 'None'}...")
    logger.info(f"OPENAI_MODEL: {OPENAI_MODEL}")
    
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key non configurata")
        return "⚠️ L'AI non è configurata. Contatta l'amministratore."
    
    if not prompt or not prompt.strip():
        logger.warning("Prompt vuoto ricevuto")
        return "⚠️ Messaggio vuoto ricevuto. Prova a scrivere qualcosa!"
    
    # Rileva movimenti inventario PRIMA di chiamare l'AI - ASYNC
    # Se riconosce un movimento, ritorna un marker speciale che il bot.py interpreterà
    if telegram_id:
        # Se è una conversazione generale NON relativa all'inventario, passa direttamente all'AI
        if _is_general_conversation(prompt):
            logger.info(f"[GENERAL_CONVERSATION] Rilevata conversazione generale, bypass ricerca vini")
            # Passa direttamente all'AI senza cercare vini
            # Continua oltre per chiamare l'AI normalmente
        
        # Richieste esplicite di elenco inventario: rispondi direttamente interrogando il DB
        if _is_inventory_list_request(prompt):
            return await _build_inventory_list_response(telegram_id, limit=50)

        # Richieste di riepilogo movimenti: chiedi periodo via bottoni (marker) o recupera direttamente se specificato
        is_movement_request, period = _is_movement_summary_request(prompt)
        if is_movement_request:
            logger.info(f"[MOVEMENT_SUMMARY] Richiesta movimenti riconosciuta: period={period} per prompt: {prompt[:50]}")
            if period == 'yesterday':
                # Richiesta specifica per ieri - recupera direttamente i movimenti
                try:
                    from .database_async import get_movement_summary_yesterday
                    summary = await get_movement_summary_yesterday(telegram_id)
                    return format_movement_period_summary('yesterday', summary)
                except Exception as e:
                    logger.error(f"Errore recupero movimenti ieri: {e}", exc_info=True)
                    return "⚠️ Errore nel recupero dei movimenti di ieri. Riprova."
            elif period == 'yesterday_replenished':
                # Richiesta specifica per rifornimenti di ieri - mostra solo rifornimenti
                try:
                    from .database_async import get_movement_summary_yesterday_replenished
                    summary = await get_movement_summary_yesterday_replenished(telegram_id)
                    return format_movement_period_summary('yesterday_replenished', summary)
                except Exception as e:
                    logger.error(f"Errore recupero rifornimenti ieri: {e}", exc_info=True)
                    return "⚠️ Errore nel recupero dei rifornimenti di ieri. Riprova."
            else:
                # Periodo non specificato, chiedi all'utente
                return "[[ASK_MOVES_PERIOD]]"

        movement_marker = await _check_and_process_movement(prompt, telegram_id)
        if movement_marker and movement_marker.startswith("__MOVEMENT__:"):
            return movement_marker  # Ritorna marker che verrà processato in bot.py
    
    try:
        # Prepara il contesto utente se disponibile
        user_context = ""
        specific_wine_info = ""  # Per vini cercati specificamente
        
        if telegram_id:
            try:
                user = await async_db_manager.get_user_by_telegram_id(telegram_id)  # ASYNC
                if user:
                    # Aggiungi informazioni utente
                    user_context = f"""
INFORMAZIONI UTENTE:
- Nome attività: {user.business_name or 'Non specificato'}
- Onboarding completato: {'Sì' if user.onboarding_completed else 'No'}

INVENTARIO ATTUALE:
"""
                    # Rileva se l'utente sta chiedendo informazioni su un vino specifico
                    # Pattern ordinati dalla più specifica alla più generica
                    wine_search_patterns = [
                        # Pattern 0: "che X ho/hai?" - PRIMA di altri pattern per catturare correttamente
                        r'(?:che|quale|quali)\s+(.+?)(?:\s+ho|\s+hai|\s+ci\s+sono|\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|\?|$)',
                        # Pattern 1: "quanti/quante bottiglie di X ho/hai" (MOLTO SPECIFICO)
                        r'(?:quanti|quante)\s+bottiglie?\s+di\s+(.+?)(?:\s+ho|\s+hai|\s+ci\s+sono|\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                        # Pattern 2: "quanti/quante X ho/hai" (senza "bottiglie")
                        r'(?:quanti|quante)\s+(.+?)(?:\s+ho|\s+hai|\s+ci\s+sono|\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                        # Pattern 3: "a quanto vendo/vendi X" (prezzo)
                        r'a\s+quanto\s+(?:vendo|vendi|costano|prezzo)\s+(.+)',
                        # Pattern 4: "prezzo X"
                        r'prezzo\s+(.+)',
                        # Pattern 5: "informazioni su X"
                        r'(?:informazioni|dettagli|info)\s+(?:su|del|dello|della)\s+(.+)',
                        # Pattern 6: "X in cantina/magazzino" (generico, solo se altri non matchano)
                        r'(.+?)(?:\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                    ]
                    
                    wine_search_term = None
                    for pattern in wine_search_patterns:
                        match = re.search(pattern, prompt.lower())
                        if match:
                            raw_term = match.group(1).strip()
                            # Pulisci il termine rimuovendo parole interrogative, articoli, ecc.
                            # ma preserva quelle che fanno parte del nome (es. "del" in "Ca del Bosco")
                            wine_search_term = _clean_wine_search_term(raw_term)
                            if wine_search_term and len(wine_search_term) > 2:  # Almeno 3 caratteri
                                logger.info(f"[WINE_SEARCH] Pattern matchato: '{pattern[:50]}...' | Termine estratto: '{raw_term}' → pulito: '{wine_search_term}'")
                                break
                    
                    # Se è stata rilevata una ricerca, cerca nel database - ASYNC
                    # Ma solo se NON è una conversazione generale
                    if wine_search_term and not _is_general_conversation(prompt):
                        found_wines = await async_db_manager.search_wines(telegram_id, wine_search_term, limit=50)
                        if found_wines:
                            # Prova a generare risposta pre-formattata (bypass AI per domande specifiche)
                            formatted_response = _format_wine_response_directly(prompt, telegram_id, found_wines)
                            if formatted_response:
                                logger.info(f"[FORMATTED] Risposta pre-formattata generata per domanda specifica")
                                return formatted_response
                            
                            # Usa format_wines_response_by_count per gestire automaticamente 1/multi/10+ vini
                            logger.info(f"[WINE_SELECTION] Trovati {len(found_wines)} vini per '{wine_search_term}'")
                            return await format_wines_response_by_count(found_wines, telegram_id)
                            
                            # Se non è una domanda specifica, passa info all'AI nel contesto
                            specific_wine_info = "\n\nVINI TROVATI NEL DATABASE PER LA RICERCA:\n"
                            for wine in found_wines:
                                info_parts = [f"- {wine.name}"]
                                if wine.vintage:
                                    info_parts.append(f"Annata: {wine.vintage}")
                                if wine.producer:
                                    info_parts.append(f"Produttore: {wine.producer}")
                                if wine.quantity is not None:
                                    info_parts.append(f"Quantità: {wine.quantity} bottiglie")
                                if wine.selling_price:
                                    info_parts.append(f"Prezzo vendita: €{wine.selling_price:.2f}")
                                if wine.cost_price:
                                    info_parts.append(f"Prezzo acquisto: €{wine.cost_price:.2f}")
                                if wine.region:
                                    info_parts.append(f"Regione: {wine.region}")
                                if wine.country:
                                    info_parts.append(f"Paese: {wine.country}")
                                specific_wine_info += " | ".join(info_parts) + "\n"
                        else:
                            specific_wine_info = f"\n\nNESSUN VINO TROVATO nel database per '{wine_search_term}'\n"
                            # Anche se non trovato, passa all'AI per gestire il messaggio
                            # (AI dirà "non ho questa informazione" in modo più naturale)
                    else:
                        # Retry 1: ricerca ampia usando l'intero prompt come termine di ricerca
                        try:
                            broad_term = re.sub(r"[^\w\s'’]", " ", prompt.lower()).strip()
                            if broad_term and len(broad_term) > 2:
                                logger.info(f"[FALLBACK] Tentativo ricerca diretta con termine: '{broad_term}'")
                                broad_found = await async_db_manager.search_wines(telegram_id, broad_term, limit=50)
                                if broad_found:
                                    logger.info(f"[FALLBACK] Trovati {len(broad_found)} vini con ricerca diretta")
                                    # Usa format_wines_response_by_count per gestire 1/multi/10+ vini
                                    return await format_wines_response_by_count(broad_found, telegram_id, query_context=f"per '{broad_term}'")
                        except Exception as e:
                            logger.warning(f"Broad search fallback failed: {e}")
                    
                    # Ottieni statistiche inventario (non tutti i vini)
                    wines = await async_db_manager.get_user_wines(telegram_id)  # ASYNC
                    if wines:
                        user_context += f"- Totale vini: {len(wines)}\n"
                        user_context += f"- Quantità totale: {sum(w.quantity for w in wines)} bottiglie\n"
                        low_stock = [w for w in wines if w.quantity <= w.min_quantity]
                        user_context += f"- Scorte basse: {len(low_stock)} vini\n"
                        user_context += "\nNOTA: I dettagli dei vini specifici vengono cercati direttamente nel database quando richiesto.\n"
                    else:
                        user_context += "- Inventario vuoto\n"
                    
                    # Nota: I movimenti inventario sono ora gestiti dalla tabella "Consumi e rifornimenti"
                    # I log interazione contengono solo messaggi utente, non movimenti
                    # user_context += "\nMOVIMENTI RECENTI:\n"  # Disabilitato - usa tabella Consumi
            except Exception as e:
                logger.error(f"Errore accesso database per utente {telegram_id}: {e}")
                user_context = "- Database temporaneamente non disponibile\n"
        
        # Sistema prompt con contesto
        system_prompt = f"""Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario vini. Sei gentile, professionale e parli in italiano.

IMPORTANTE - INTERPRETAZIONE SINONIMI GEOGRAFICI:
Quando l'utente menziona paesi o regioni, interpreta correttamente i sinonimi:
- "stati uniti", "stati uniti d'america", "america", "united states", "us" → country: "USA"
- "italia", "italiano", "italiani", "italiane", "italy" → country: "Italia"
- "francia", "francese", "francesi", "france" → country: "Francia"
- "spagna", "spagnolo", "spagnoli", "spain" → country: "Spagna"
- "germania", "tedesco", "tedeschi", "germany" → country: "Germania"
- "portogallo", "portoghese", "portoghesi", "portugal" → country: "Portogallo"
- "australia", "australiano", "australiani" → country: "Australia"
- "cile", "cileno", "cileni", "chile" → country: "Cile"
- "argentina", "argentino", "argentini" → country: "Argentina"

Per regioni italiane:
- "toscana", "toscano", "toscani" → region: "Toscana"
- "piemonte", "piemontese", "piemontesi" → region: "Piemonte"
- "veneto", "veneti" → region: "Veneto"
- "lombardia", "lombardo", "lombardi" → region: "Lombardia"
- E così via per altre regioni italiane

Quando l'utente chiede "vini italiani" o "vini degli stati uniti", usa sempre la funzione search_wines con filtri corretti (country/region), NON cercare come nome vino.

{user_context}{specific_wine_info}

CAPACITÀ:
- Analizzare l'inventario dell'utente in tempo reale
- Rispondere a QUALSIASI domanda o messaggio
- Suggerire riordini per scorte basse
- Fornire consigli pratici su gestione magazzino
- Analizzare movimenti e consumi
- Generare report e statistiche
- Conversazione naturale e coinvolgente
- Generare link per visualizzare l'inventario

ISTRUZIONI IMPORTANTI:
- CONSULTA SEMPRE il database prima di rispondere a qualsiasi domanda informativa
- RISPONDI SEMPRE a qualsiasi messaggio, anche se non è una domanda
- Mantieni una conversazione naturale e amichevole
- Usa sempre i dati dell'inventario e dei movimenti quando disponibili
- Sii specifico e pratico nei consigli
- Se l'utente comunica consumi/rifornimenti, conferma e analizza
- Suggerisci comandi del bot quando appropriato (es: /view, /log)
- Se l'inventario ha scorte basse, avvisa proattivamente
- Se l'utente fa domande generiche, usa il contesto per essere specifico
- Se l'utente chiede di vedere tutti i vini o l'inventario completo, usa la funzione tool "generate_view_link" per inviare il link del viewer

GESTIONE QUERY QUALITATIVE E SENSORIALI:
- Se l'utente chiede "più pregiato", "migliore", "di valore", "prestigioso" → usa get_wine_by_criteria con query_type: "max", field: "selling_price"
- Se l'utente chiede "più economico", "meno costoso" → usa get_wine_by_criteria con query_type: "min", field: "selling_price"
- Se l'utente chiede "più recente", "più nuovo" → usa get_wine_by_criteria con query_type: "max", field: "vintage"
- Se l'utente chiede "più vecchio", "più antico" → usa get_wine_by_criteria con query_type: "min", field: "vintage"
- Se l'utente chiede caratteristiche sensoriali come "più tannico", "più corposo", "più floreale", "più secco", "più boccato":
  Il sistema cerca automaticamente nei campi description/notes, usa mappatura euristica (wine_type + alcohol_content) e mappatura per uvaggi tipici
- MAI rispondere "vino non trovato" o "errore temporaneo" a domande qualitative o sensoriali: accedi sempre al database e ragiona sui dati disponibili

REGOLA CRITICA PER RICERCHE FILTRATE:
- Se l'utente chiede vini con QUALSIASI filtro geografico/tipo/prezzo/annata (es. "della Toscana", "italiani", "rossi", "sotto €50"), DEVI chiamare search_wines con i filtri estratti
- NON usare get_inventory_list se ci sono filtri nella richiesta
- Estrai filtri dal testo: "della Toscana" → {{"region": "Toscana"}}, "italiani" → {{"country": "Italia"}}, "rossi" → {{"wine_type": "rosso"}}
- Combina filtri quando presenti: "rossi italiani" → {{"country": "Italia", "wine_type": "rosso"}}

FORMATO RISPOSTE PRE-STRUTTURATE:
Per domande informative, usa questi formati con dati reali dal database:

1. ELENCO INVENTARIO ("che vini ho?", "lista inventario"):
📋 **Il tuo inventario**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Nome Vino (Produttore) Annata — quantità bott. - €prezzo
2. ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2. QUANTITÀ VINO ("quanti X ho?"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 **In cantina hai:** X bottiglie
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3. PREZZO VINO ("a quanto vendo X?"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Prezzo vendita:** €XX.XX
💵 **Prezzo acquisto:** €XX.XX
📊 **Margine:** €XX.XX (XX%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

4. INFO COMPLETE VINO ("dimmi tutto su X"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏭 **Produttore:** ...
📍 **Regione:** ...
📅 **Annata:** ...
🍇 **Vitigno:** ...
📦 **Quantità:** X bottiglie
🔴/⚪ **Tipo:** ...
⭐ **Classificazione:** ...
💰 **Prezzo vendita:** €XX.XX
💵 **Prezzo acquisto:** €XX.XX
🍾 **Gradazione:** XX% vol
📝 **Descrizione:** ...
💬 **Note:** ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

5. VINO NON TROVATO:
❌ **Vino non trovato**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Non ho trovato 'nome' nel tuo inventario.
💡 **Cosa puoi fare:**
• Controlla l'ortografia del nome
• Usa /view per vedere tutti i vini
• Usa /aggiungi per aggiungere un nuovo vino
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

6. VINO PRESENTE ("X c'è?"):
✅ **Sì, ce l'hai!**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🍷 **Nome Vino (Produttore)** con X bottiglie
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REGOLA D'ORO: Prima di rispondere a qualsiasi domanda informativa, consulta SEMPRE il database usando i dati forniti nel contesto o cerca il vino specifico se necessario."""
        
        # Suggerimento forte per l'AI: se la richiesta corrisponde a uno dei casi (quantità, prezzo, info vino, elenco),
        # usa il formato pre-strutturato corrispondente. Solo se non applicabile, rispondi in modo colloquiale
        # ma sempre basandoti sui dati del database quando disponibili.
        
        logger.info(f"System prompt length: {len(system_prompt)}")
        logger.info(f"User prompt: {prompt[:100]}...")

        # Recupera storico conversazione (ultimi 10 messaggi) e costruisci chat
        history_messages = []
        if telegram_id:
            try:
                history = await async_db_manager.get_recent_chat_messages(telegram_id, limit=10)
                for h in history:
                    if h.get('role') in ('user', 'assistant') and h.get('content'):
                        history_messages.append({"role": h['role'], "content": h['content']})
            except Exception as e:
                logger.warning(f"Impossibile recuperare chat history per {telegram_id}: {e}")

        # Configura client OpenAI versione 2.x
        try:
            import openai
            logger.info(f"OpenAI version: {openai.__version__}")
            
            # Crea client OpenAI con configurazione semplice
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            logger.info("Client OpenAI creato con successo")
        except Exception as e:
            logger.error(f"Errore creazione client OpenAI: {e}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            logger.error(f"Errore completo: {str(e)}")
            return "Ciao! 👋 Sono Gio.ia-bot, il tuo assistente per la gestione inventario vini. Al momento l'AI è temporaneamente non disponibile, ma puoi usare i comandi /help per vedere le funzionalità disponibili!"
        # Definizione tools (function calling) per accesso deterministico ai dati
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_list",
                    "description": "Restituisce l'elenco dei vini dell'utente corrente con quantità e prezzi.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Numero massimo di vini da elencare", "default": 50}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_info",
                    "description": "Restituisce le informazioni dettagliate di un vino presente nell'inventario utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino da cercare"}
                        },
                        "required": ["wine_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_price",
                    "description": "Restituisce i prezzi (vendita/acquisto) per un vino dell'utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino"}
                        },
                        "required": ["wine_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_quantity",
                    "description": "Restituisce la quantità in magazzino per un vino dell'utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino"}
                        },
                        "required": ["wine_query"]
                    }
                }
            }
        ]
        # Domande informative generiche (quale vino ha meno quantità, quale è il più costoso, ecc.)
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "get_wine_by_criteria",
                    "description": """Trova il vino che corrisponde a criteri specifici (min/max per quantità, prezzo, annata).
                    Usa questa funzione quando l'utente chiede domande qualitative o comparative:
                    - "quale vino ha meno quantità" → query_type: "min", field: "quantity"
                    - "quale è il più costoso/pregiato/migliore/valore/prestigio" → query_type: "max", field: "selling_price"
                    - "quale ha più bottiglie" → query_type: "max", field: "quantity"
                    - "quale è il più economico" → query_type: "min", field: "selling_price"
                    - "quale vino ho pagato di più" → query_type: "max", field: "cost_price"
                    - "quale è il più recente/nuovo" → query_type: "max", field: "vintage"
                    - "quale è il più vecchio/antico" → query_type: "min", field: "vintage"
                    
                    IMPORTANTE: "pregiato", "migliore", "di valore", "prestigioso" generalmente si riferiscono al prezzo più alto (selling_price max).
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query_type": {
                                "type": "string",
                                "enum": ["min", "max"],
                                "description": "Tipo di query: 'min' per trovare il minimo, 'max' per trovare il massimo"
                            },
                            "field": {
                                "type": "string",
                                "enum": ["quantity", "selling_price", "cost_price", "vintage"],
                                "description": "Campo da interrogare: 'quantity' per quantità bottiglie, 'selling_price' per prezzo vendita, 'cost_price' per prezzo acquisto, 'vintage' per annata"
                            }
                        },
                        "required": ["query_type", "field"]
                    }
                }
            }
        ])
        
        # Ricerca filtrata e riepilogo inventario
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "search_wines",
                    "description": """Cerca vini applicando filtri multipli. USA QUESTA FUNZIONE quando l'utente chiede vini con criteri specifici:
- Geografici: 'della Toscana', 'italiani', 'del Piemonte', 'francesi', ecc.
- Tipo: 'rossi', 'bianchi', 'spumanti', 'rosati'
- Prezzo: 'prezzo sotto X', 'prezzo sopra Y'
- Annata: 'dal 2015', 'fino al 2020'
- Produttore: 'produttore X', 'cantina Y'
- Combinati: 'rossi toscani', 'italiani sotto €50'

IMPORTANTE: Se la richiesta contiene QUALSIASI filtro, usa questa funzione invece di get_inventory_list.
Formato filters: {"region": "Toscana", "country": "Italia", "wine_type": "rosso", "price_max": 50, "vintage_min": 2015, "producer": "nome", "name_contains": "testo"}""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filters": {
                                "type": "object",
                                "properties": {
                                    "region": {"type": "string", "description": "Regione italiana (es. 'Toscana', 'Piemonte')"},
                                    "country": {"type": "string", "description": "Paese (es. 'Italia', 'Francia', 'Spagna')"},
                                    "wine_type": {"type": "string", "enum": ["rosso", "bianco", "rosato", "spumante"]},
                                    "classification": {"type": "string"},
                                    "producer": {"type": "string", "description": "Nome produttore/cantina"},
                                    "name_contains": {"type": "string", "description": "Testo contenuto nel nome vino"},
                                    "price_min": {"type": "number", "description": "Prezzo minimo vendita"},
                                    "price_max": {"type": "number", "description": "Prezzo massimo vendita"},
                                    "vintage_min": {"type": "integer", "description": "Annata minima (es. 2015)"},
                                    "vintage_max": {"type": "integer", "description": "Annata massima (es. 2020)"},
                                    "quantity_min": {"type": "integer"},
                                    "quantity_max": {"type": "integer"}
                                }
                            },
                            "limit": {"type": "integer", "default": 50}
                        },
                        "required": ["filters"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_stats",
                    "description": "Ritorna il riepilogo inventario (totale vini, totale bottiglie, prezzi media/min/max, low stock).",
                    "parameters": {"type": "object", "properties": {}},
                }
            }
        ])
        tools.append({
            "type": "function",
            "function": {
                "name": "get_movement_summary",
                "description": "Riepiloga consumi/rifornimenti per un periodo (day/week/month). Se periodo mancante, chiedilo all'utente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "period": {"type": "string", "enum": ["day", "week", "month"], "description": "Periodo del riepilogo"}
                    },
                    "required": []
                }
            }
        })
        # ✅ NUOVI TOOL: Movimenti e funzioni aggiuntive
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "register_consumption",
                    "description": "Registra un consumo (vendita/consumo) di bottiglie. Diminuisce la quantità disponibile del vino specificato.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_name": {"type": "string", "description": "Nome del vino da consumare"},
                            "quantity": {"type": "integer", "description": "Numero di bottiglie consumate (deve essere positivo)"}
                        },
                        "required": ["wine_name", "quantity"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "register_replenishment",
                    "description": "Registra un rifornimento (acquisto/aggiunta) di bottiglie. Aumenta la quantità disponibile del vino specificato.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_name": {"type": "string", "description": "Nome del vino da rifornire"},
                            "quantity": {"type": "integer", "description": "Numero di bottiglie aggiunte (deve essere positivo)"}
                        },
                        "required": ["wine_name", "quantity"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_low_stock_wines",
                    "description": "Ottiene lista vini con scorte basse (quantità inferiore alla soglia). Utile per identificare vini da rifornire.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "threshold": {"type": "integer", "description": "Soglia minima quantità (vini con quantità < threshold vengono segnalati)", "default": 5}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_details",
                    "description": "Ottiene dettagli completi di un vino specifico: nome, produttore, annata, quantità, prezzo, regione, tipo, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_id": {"type": "integer", "description": "ID del vino di cui ottenere i dettagli"}
                        },
                        "required": ["wine_id"]
                    }
                }
            }
        ])

        # Chiamata API con gestione errori robusta
        try:
            logger.info(f"Chiamata API OpenAI - Model: {OPENAI_MODEL}")
            messages = [{"role": "system", "content": system_prompt}]
            # Aggiungi storico conversazione (già normalizzato)
            messages.extend(history_messages)
            # Aggiungi ultimo messaggio utente
            messages.append({"role": "user", "content": prompt.strip()})

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
                tools=tools,
                tool_choice="auto"
            )
            logger.info("Chiamata API OpenAI completata con successo")
        except Exception as e:
            logger.error(f"Errore chiamata API OpenAI: {e}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            # Fallback: se la richiesta contiene filtri riconoscibili, esegui ricerca locale senza AI
            try:
                if telegram_id:
                    derived = _parse_filters(prompt)
                    if derived:
                        wines = await async_db_manager.search_wines_filtered(telegram_id, derived, limit=50)
                        if wines:
                            return format_inventory_list(wines, limit=50)
                        return format_search_no_results(derived)
            except Exception as fe:
                logger.error(f"Fallback ricerca filtrata fallito: {fe}")
            return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
        
        # Se l'AI ha scelto di chiamare un tool, gestiscilo qui (function calling)
        choice = response.choices[0]
        message = choice.message

        # Gestione tool calls
        try:
            tool_calls = getattr(message, "tool_calls", None)
        except Exception:
            tool_calls = None

        if tool_calls and telegram_id:
            # Esegui la prima tool call rilevante (una risposta deterministica e rapida)
            call = tool_calls[0]
            fn = call.function
            name = getattr(fn, "name", "")
            import json as _json
            args = {}
            try:
                args = _json.loads(getattr(fn, "arguments", "{}") or "{}")
            except Exception:
                args = {}

            logger.info(f"[TOOLS] AI ha richiesto tool: {name} args={args}")

            # ✅ USA FUNCTION EXECUTOR (centralizzato) - gestione graceful se modulo mancante
            try:
                from .function_executor import FunctionExecutor
                
                # Crea executor (context non disponibile in ai.py, passa None)
                executor = FunctionExecutor(telegram_id, None)
                result = await executor.execute_function(name, args)
                
                # ✅ Se template disponibile, usa direttamente (NO re-chiamata AI)
                if result.get("use_template") and result.get("formatted_message"):
                    logger.info(f"[TOOLS] Risposta formattata con template (NO re-chiamata AI)")
                    return result["formatted_message"]
                
                # Se success ma no template, ritorna messaggio di successo
                if result.get("success"):
                    return result.get("formatted_message", result.get("message", "✅ Operazione completata"))
                
                # Se errore, ritorna messaggio errore
                error_msg = result.get("error", "Errore sconosciuto")
                return f"❌ {error_msg}"
                
            except ImportError:
                # FunctionExecutor non disponibile, usa fallback inline (compatibilità)
                logger.debug(f"[TOOLS] FunctionExecutor non disponibile, usando fallback inline per tool '{name}'")
                # Passa al fallback inline
            except Exception as e:
                logger.error(f"[TOOLS] Errore FunctionExecutor per tool '{name}': {e}", exc_info=True)
                # Fallback a logica inline
            
            # ✅ FALLBACK: Implementazioni tool inline (per compatibilità)
            if name == "get_inventory_list":
                limit = int(args.get("limit", 50))
                return await _build_inventory_list_response(telegram_id, limit=limit)

            if name == "generate_view_link":
                return "Puoi usare il comando /view per ottenere il link al viewer dell'inventario."

            if name == "get_wine_info":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                
                # ✅ CASCADING RETRY: Prova ricerca con retry a livelli
                from .database_async import async_db_manager
                wines, retry_query_used, level_used = await _cascading_retry_search(
                    telegram_id=telegram_id,
                    original_query=query,
                    search_func=async_db_manager.search_wines,
                    search_func_args={"telegram_id": telegram_id, "search_term": query, "limit": 10},
                    original_filters=None
                )
                
                if wines:
                    logger.info(f"[GET_WINE_INFO] ✅ Trovati {len(wines)} vini (livello: {level_used}, query: {retry_query_used or query})")
                    # Se ci sono più vini, mostra bottoni per selezione
                    if len(wines) > 1:
                        logger.info(f"[GET_WINE_INFO] Mostro bottoni per selezione")
                        wine_ids = [str(w.id) for w in wines[:10]]  # Max 10 bottoni
                        return f"[[WINE_SELECTION_BUTTONS:{':'.join(wine_ids)}]]"
                    # Se c'è solo un vino, mostra info dettagliata
                    return format_wine_info(wines[0])
                
                return format_wine_not_found(query)

            if name == "get_wine_price":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                
                # ✅ CASCADING RETRY: Prova ricerca con retry a livelli
                from .database_async import async_db_manager
                wines, retry_query_used, level_used = await _cascading_retry_search(
                    telegram_id=telegram_id,
                    original_query=query,
                    search_func=async_db_manager.search_wines,
                    search_func_args={"telegram_id": telegram_id, "search_term": query, "limit": 50},
                    original_filters=None
                )
                
                if wines:
                    logger.info(f"[GET_WINE_PRICE] ✅ Trovati {len(wines)} vini (livello: {level_used}, query: {retry_query_used or query})")
                    return await format_wines_response_by_count(wines, telegram_id)
                
                return format_wine_not_found(query)

            if name == "get_wine_quantity":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                
                # ✅ CASCADING RETRY: Prova ricerca con retry a livelli
                from .database_async import async_db_manager
                wines, retry_query_used, level_used = await _cascading_retry_search(
                    telegram_id=telegram_id,
                    original_query=query,
                    search_func=async_db_manager.search_wines,
                    search_func_args={"telegram_id": telegram_id, "search_term": query, "limit": 50},
                    original_filters=None
                )
                
                if wines:
                    logger.info(f"[GET_WINE_QUANTITY] ✅ Trovati {len(wines)} vini (livello: {level_used}, query: {retry_query_used or query})")
                    return await format_wines_response_by_count(wines, telegram_id)
                
                return format_wine_not_found(query)

            if name == "search_wines":
                filters = args.get("filters") or {}
                limit = int(args.get("limit", 50))
                
                # Arricchisci filtri dal prompt (parser fallback se AI non ha estratto tutto)
                derived = _parse_filters(prompt)
                # Merge: derived ha priorità (più accurato), poi filtri AI, poi derived se mancanti
                merged_filters = {**filters, **{k: v for k, v in derived.items() if k not in filters or not filters.get(k)}}
                
                logger.info(f"[SEARCH] Filtri applicati: {merged_filters}")
                
                # ✅ CASCADING RETRY: Prova ricerca filtrata con retry a livelli
                from .database_async import async_db_manager
                
                # Estrai query originale dai filtri per retry
                original_query = None
                if "producer" in merged_filters and merged_filters["producer"]:
                    original_query = merged_filters["producer"]
                elif "name_contains" in merged_filters and merged_filters["name_contains"]:
                    original_query = merged_filters["name_contains"]
                
                wines, retry_query_used, level_used = await _cascading_retry_search(
                    telegram_id=telegram_id,
                    original_query=original_query or prompt,
                    search_func=async_db_manager.search_wines_filtered,
                    search_func_args={"telegram_id": telegram_id, "filters": merged_filters, "limit": limit},
                    original_filters=merged_filters
                )
                
                if wines:
                    logger.info(f"[SEARCH] ✅ Trovati {len(wines)} vini (livello: {level_used}, query: {retry_query_used or original_query})")
                    # Usa format_wines_response_by_count per gestire automaticamente i casi
                    return await format_wines_response_by_count(wines, telegram_id)
                
                return format_search_no_results(merged_filters)

            if name == "get_inventory_stats":
                stats = await async_db_manager.get_inventory_stats(telegram_id)
                return format_inventory_summary(
                    telegram_id,
                    stats.get('total_wines', 0),
                    stats.get('total_bottles', 0),
                    stats.get('low_stock', 0)
                )

            if name == "get_movement_summary":
                period = (args.get("period") or "").strip()
                if not period:
                    return "[[ASK_MOVES_PERIOD]]"
                try:
                    totals = await get_movement_summary(telegram_id, period)
                    return format_movement_period_summary(period, totals)
                except Exception as e:
                    logger.error(f"Errore get_movement_summary tool: {e}")
                    return "⚠️ Errore nel calcolo dei movimenti. Riprova."
            
            if name == "get_wine_by_criteria":
                query_type = args.get("query_type")
                field = args.get("field")
                if not query_type or not field:
                    return "❌ Richiesta incompleta: specifica query_type (min/max) e field (quantity/selling_price/cost_price/vintage)."
                
                logger.info(f"[GET_WINE_BY_CRITERIA] AI ha richiesto: {query_type} {field}")
                response = await _handle_informational_query(telegram_id, query_type, field)
                if response:
                    return response
                return "❌ Non ho trovato vini che corrispondono ai criteri richiesti."
            
            # Tool non riconosciuto
            logger.warning(f"[TOOLS] Tool '{name}' non riconosciuto nel fallback")
            return f"⚠️ Funzione '{name}' non ancora implementata."

        # Nessuna tool call: usa il contenuto generato
        content = getattr(message, "content", "") or ""
        if not content.strip():
            logger.error("Risposta vuota da OpenAI")
            return "⚠️ Errore nella generazione della risposta. Riprova."
        
        # ✅ FALLBACK: Se la risposta contiene errori "vino non trovato" o simili,
        # prova a interpretare la query come domanda qualitativa e accedi al database
        content_lower = content.lower()
        if telegram_id and any(phrase in content_lower for phrase in [
            "vino non trovato", "non ho trovato", "non trovato", "not found",
            "non è presente", "non presente nell'inventario"
        ]):
            logger.info(f"[FALLBACK] AI ha risposto con 'non trovato', provo interpretazione query qualitativa: {prompt}")
            
            # Prova a interpretare la domanda come query qualitativa
            fallback_response = await _handle_qualitative_query_fallback(telegram_id, prompt)
            if fallback_response:
                logger.info(f"[FALLBACK] Trovata risposta qualitativa, uso quella invece di risposta AI")
                return fallback_response
        
        return content.strip()
        
    except OpenAIError as e:
        logger.error(f"Errore OpenAI: {e}")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
    except Exception as e:
        logger.error(f"Errore imprevisto in get_ai_response: {e}")
        logger.error(f"Tipo errore: {type(e).__name__}")
        logger.error(f"Prompt ricevuto: {prompt[:100]}...")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."



