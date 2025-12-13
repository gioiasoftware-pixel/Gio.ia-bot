"""
Utility condivise per gestione movimenti inventario.
Include fuzzy matching e gestione errori centralizzata.
"""
import logging
from typing import List, Optional, Any, Tuple, Dict
from .database_async import async_db_manager

logger = logging.getLogger(__name__)


async def _cascading_retry_search_for_movement(
    telegram_id: int,
    original_query: str,
    search_func,
    search_func_args: Dict[str, Any],
    original_filters: Optional[Dict[str, Any]] = None
) -> tuple[Optional[List], Optional[str], str]:
    """
    Wrapper per _cascading_retry_search da ai.py per evitare import circolari.
    Esegue ricerca con cascata di retry a 3 livelli per movimenti.
    
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
    # Import qui per evitare import circolari
    from .ai import _cascading_retry_search
    return await _cascading_retry_search(
        telegram_id=telegram_id,
        original_query=original_query,
        search_func=search_func,
        search_func_args=search_func_args,
        original_filters=original_filters
    )


async def fuzzy_match_wine_name(
    telegram_id: int, 
    wine_name: str, 
    limit: int = 10,
    price_filters: Optional[Dict[str, Optional[float]]] = None
) -> List[Any]:
    """
    Cerca vini con fuzzy matching migliorato.
    Supporta:
    1. Ricerca normale con search_wines (con filtri prezzo se presenti)
    2. Ricerca per primi caratteri se non trova match
    3. Fuzzy matching con rapidfuzz se disponibile
    
    Args:
        telegram_id: ID Telegram utente
        wine_name: Nome vino da cercare
        limit: Limite risultati
        price_filters: Dict opzionale con filtri prezzo (price_min, price_max, cost_min, cost_max, price_around, cost_around)
    
    Returns:
        Lista di vini corrispondenti
    """
    # Se ci sono filtri di prezzo, usa search_wines_filtered
    if price_filters and any(v is not None for v in price_filters.values()):
        # Converti filtri per search_wines_filtered
        search_filters = {}
        
        # Gestisci price_around (range ±10% o ±5€)
        if price_filters.get('price_around') is not None:
            price = price_filters['price_around']
            tolerance = max(price * 0.1, 5.0)
            search_filters['price_min'] = price - tolerance
            search_filters['price_max'] = price + tolerance
        else:
            if price_filters.get('price_min') is not None:
                search_filters['price_min'] = price_filters['price_min']
            if price_filters.get('price_max') is not None:
                search_filters['price_max'] = price_filters['price_max']
        
        # Gestisci cost_around
        if price_filters.get('cost_around') is not None:
            cost = price_filters['cost_around']
            tolerance = max(cost * 0.1, 5.0)
            search_filters['cost_price_min'] = cost - tolerance
            search_filters['cost_price_max'] = cost + tolerance
        else:
            if price_filters.get('cost_min') is not None:
                search_filters['cost_price_min'] = price_filters['cost_min']
            if price_filters.get('cost_max') is not None:
                search_filters['cost_price_max'] = price_filters['cost_max']
        
        # Cerca prima per nome/produttore/uvaggio con filtri prezzo - usa cascading retry
        if wine_name:
            # Usa search_wines_filtered con name_contains (cerca in name, producer, grape_variety)
            search_filters['name_contains'] = wine_name
            matching_wines, retry_query_used, level_used = await _cascading_retry_search_for_movement(
                telegram_id=telegram_id,
                original_query=wine_name,
                search_func=async_db_manager.search_wines_filtered,
                search_func_args={"telegram_id": telegram_id, "filters": search_filters, "limit": limit},
                original_filters=search_filters
            )
            if matching_wines:
                logger.info(f"[FUZZY_MATCH] Trovati {len(matching_wines)} vini con filtri prezzo per '{wine_name}' (livello: {level_used}, query: {retry_query_used or wine_name})")
                return matching_wines
            
            # Se non trova con name_contains, prova anche con producer e grape_variety - usa cascading retry
            # Rimuovi name_contains e aggiungi producer
            search_filters_producer = search_filters.copy()
            search_filters_producer.pop('name_contains', None)
            search_filters_producer['producer'] = wine_name
            matching_wines, retry_query_used, level_used = await _cascading_retry_search_for_movement(
                telegram_id=telegram_id,
                original_query=wine_name,
                search_func=async_db_manager.search_wines_filtered,
                search_func_args={"telegram_id": telegram_id, "filters": search_filters_producer, "limit": limit},
                original_filters=search_filters_producer
            )
            if matching_wines:
                logger.info(f"[FUZZY_MATCH] Trovati {len(matching_wines)} vini con filtri prezzo per producer '{wine_name}' (livello: {level_used}, query: {retry_query_used or wine_name})")
                return matching_wines
    
    # 1. Ricerca normale (senza filtri prezzo o se non ha trovato con filtri) - usa cascading retry
    matching_wines, retry_query_used, level_used = await _cascading_retry_search_for_movement(
        telegram_id=telegram_id,
        original_query=wine_name,
        search_func=async_db_manager.search_wines,
        search_func_args={"telegram_id": telegram_id, "search_term": wine_name, "limit": limit},
        original_filters=None
    )
    
    if matching_wines:
        logger.info(f"[FUZZY_MATCH] Trovati {len(matching_wines)} vini per '{wine_name}' (livello: {level_used}, query: {retry_query_used or wine_name})")
        
        # Se ci sono filtri prezzo, filtra i risultati
        if price_filters and any(v is not None for v in price_filters.values()):
            filtered_wines = []
            for wine in matching_wines:
                # Controlla price_min
                if price_filters.get('price_min') is not None:
                    if wine.selling_price is None or wine.selling_price < price_filters['price_min']:
                        continue
                # Controlla price_max
                if price_filters.get('price_max') is not None:
                    if wine.selling_price is None or wine.selling_price > price_filters['price_max']:
                        continue
                # Controlla price_around
                if price_filters.get('price_around') is not None:
                    price = price_filters['price_around']
                    tolerance = max(price * 0.1, 5.0)
                    if wine.selling_price is None or abs(wine.selling_price - price) > tolerance:
                        continue
                # Controlla cost_min
                if price_filters.get('cost_min') is not None:
                    if wine.cost_price is None or wine.cost_price < price_filters['cost_min']:
                        continue
                # Controlla cost_max
                if price_filters.get('cost_max') is not None:
                    if wine.cost_price is None or wine.cost_price > price_filters['cost_max']:
                        continue
                # Controlla cost_around
                if price_filters.get('cost_around') is not None:
                    cost = price_filters['cost_around']
                    tolerance = max(cost * 0.1, 5.0)
                    if wine.cost_price is None or abs(wine.cost_price - cost) > tolerance:
                        continue
                filtered_wines.append(wine)
            
            if filtered_wines:
                logger.info(f"[FUZZY_MATCH] Filtro prezzo applicato: {len(matching_wines)} → {len(filtered_wines)} vini")
                return filtered_wines
            # Se filtri prezzo non hanno dato risultati, continua con ricerca normale
        
        return matching_wines
    
    # 2. Se non trova, prova ricerca per primi caratteri - usa cascading retry
    if len(wine_name) >= 4:
        short_search = wine_name[:4].lower()
        matching_wines, retry_query_used, level_used = await _cascading_retry_search_for_movement(
            telegram_id=telegram_id,
            original_query=short_search,
            search_func=async_db_manager.search_wines,
            search_func_args={"telegram_id": telegram_id, "search_term": short_search, "limit": limit},
            original_filters=None
        )
        if matching_wines:
            logger.info(f"[FUZZY_MATCH] Trovato match con primi caratteri '{short_search}' per '{wine_name}' (livello: {level_used}, query: {retry_query_used or short_search})")
            return matching_wines
    
    # 3. Se ancora non trova, usa rapidfuzz per fuzzy matching su tutti i vini
    # Cerca sia nel nome che nell'uvaggio (grape_variety)
    try:
        from rapidfuzz import fuzz, process
        all_wines = await async_db_manager.get_user_wines(telegram_id)
        
        if all_wines:
            # Crea lista di stringhe da cercare: nome vino + uvaggio (se presente)
            search_strings = []
            wine_to_string = {}  # Mappa stringa -> vino per recupero
            
            for wine in all_wines:
                # Aggiungi nome vino
                if wine.name:
                    search_strings.append(wine.name.lower())
                    wine_to_string[wine.name.lower()] = wine
                
                # Aggiungi uvaggio se presente
                if wine.grape_variety:
                    grape_lower = wine.grape_variety.lower()
                    search_strings.append(grape_lower)
                    wine_to_string[grape_lower] = wine
                    
                    # Aggiungi anche combinazione nome + uvaggio
                    if wine.name:
                        combined = f"{wine.name.lower()} {grape_lower}"
                        search_strings.append(combined)
                        wine_to_string[combined] = wine
            
            if search_strings:
                best_match = process.extractOne(
                    wine_name.lower(),
                    search_strings,
                    scorer=fuzz.WRatio,  # Weighted Ratio (migliore per typo)
                    score_cutoff=70  # Minimo 70% di similarità
                )
                
                if best_match:
                    matched_string, score, _ = best_match
                    matched_wine = wine_to_string.get(matched_string)
                    
                    if matched_wine:
                        logger.info(
                            f"[FUZZY_MATCH] Rapidfuzz match: '{wine_name}' → '{matched_string}' "
                            f"(similarità: {score:.1f}%) - vino: {matched_wine.name}"
                        )
                        # Trova tutti i vini con lo stesso nome (potrebbero esserci duplicati)
                        matching_wines = [w for w in all_wines if w.id == matched_wine.id]
                        return matching_wines
    except ImportError:
        logger.debug("[FUZZY_MATCH] rapidfuzz non disponibile, skip fuzzy matching avanzato")
    except Exception as e:
        logger.warning(f"[FUZZY_MATCH] Errore fuzzy matching rapidfuzz: {e}")
    
    return []


def is_comprehension_error(error_msg: str) -> bool:
    """
    Identifica se un errore è un errore di comprensione (AI può risolvere).
    
    Args:
        error_msg: Messaggio di errore
    
    Returns:
        True se è un errore di comprensione, False se è tecnico
    """
    if not error_msg:
        return False
    
    error_lower = error_msg.lower()
    
    # Errori tecnici (NON passare all'AI) - priorità alta
    technical_indicators = [
        "business name non trovato",
        "business name non configurato",
        "onboarding",
        "timeout",
        "http error",
        "http client error",
        "connection error",
        "errore connessione",
        "nome vino o quantità non validi",
        "quantità non valida",
        "telegram_id non trovato",
        "insufficient",
        "insufficiente",
    ]
    
    # Controlla prima errori tecnici (priorità)
    for indicator in technical_indicators:
        if indicator in error_lower:
            return False
    
    # Errori di comprensione (AI può risolvere)
    comprehension_indicators = [
        "wine not found",
        "vino non trovato",
        "non ho trovato",
        "non trovato",
        "not found",
        "nessun vino",
        "nessun risultato",
        "no results",
        "errore sconosciuto",
    ]
    
    for indicator in comprehension_indicators:
        if indicator in error_lower:
            return True
    
    return False


def format_movement_error_message(wine_name: str, error_msg: str, quantity: int = None) -> str:
    """
    Formatta un messaggio di errore per movimenti in modo consistente.
    
    Args:
        wine_name: Nome del vino
        error_msg: Messaggio di errore
        quantity: Quantità richiesta (opzionale)
    
    Returns:
        Messaggio formattato per l'utente
    """
    error_lower = error_msg.lower()
    
    if 'wine_not_found' in error_lower or 'non trovato' in error_lower or 'not found' in error_lower:
        return (
            f"❌ **Vino non trovato**\n\n"
            f"Non ho trovato '{wine_name}' nel tuo inventario.\n"
            f"💡 Controlla il nome o usa `/view` per vedere i vini disponibili.\n\n"
            f"🆕 **Per aggiungere un nuovo vino:** usa `/aggiungi`"
        )
    elif 'insufficient' in error_lower or 'insufficiente' in error_lower:
        quantity_text = f"\n🍷 Richieste: {quantity} bottiglie\n" if quantity else ""
        return (
            f"⚠️ **Quantità insufficiente**\n\n"
            f"{quantity_text}"
            f"💡 Verifica la quantità disponibile con `/view`."
        )
    else:
        return (
            f"❌ **Errore durante l'aggiornamento**\n\n"
            f"{error_msg[:200]}\n\n"
            f"Riprova più tardi."
        )


def format_movement_success_message(
    movement_type: str,
    wine_name: str,
    quantity: int,
    quantity_before: int,
    quantity_after: int
) -> str:
    """
    Formatta un messaggio di successo per movimenti in modo consistente.
    
    Args:
        movement_type: 'consumo' o 'rifornimento'
        wine_name: Nome del vino
        quantity: Quantità del movimento
        quantity_before: Quantità prima
        quantity_after: Quantità dopo
    
    Returns:
        Messaggio formattato per l'utente
    """
    if movement_type == 'consumo':
        return (
            f"✅ **Consumo registrato**\n\n"
            f"🍷 **Vino:** {wine_name}\n"
            f"📦 **Quantità:** {quantity_before} → {quantity_after} bottiglie\n"
            f"📉 **Consumate:** {quantity} bottiglie\n\n"
            f"💾 **Movimento salvato** nel sistema"
        )
    else:  # rifornimento
        return (
            f"✅ **Rifornimento registrato**\n\n"
            f"🍷 **Vino:** {wine_name}\n"
            f"📦 **Quantità:** {quantity_before} → {quantity_after} bottiglie\n"
            f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
            f"💾 **Movimento salvato** nel sistema"
        )
