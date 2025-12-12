"""
Utility condivise per gestione movimenti inventario.
Include fuzzy matching e gestione errori centralizzata.
"""
import logging
from typing import List, Optional, Any, Tuple
from .database_async import async_db_manager

logger = logging.getLogger(__name__)


async def fuzzy_match_wine_name(telegram_id: int, wine_name: str, limit: int = 10) -> List[Any]:
    """
    Cerca vini con fuzzy matching migliorato.
    Supporta:
    1. Ricerca normale con search_wines
    2. Ricerca per primi caratteri se non trova match
    3. Fuzzy matching con rapidfuzz se disponibile
    
    Args:
        telegram_id: ID Telegram utente
        wine_name: Nome vino da cercare
        limit: Limite risultati
    
    Returns:
        Lista di vini corrispondenti
    """
    # 1. Ricerca normale
    matching_wines = await async_db_manager.search_wines(telegram_id, wine_name, limit=limit)
    
    if matching_wines:
        return matching_wines
    
    # 2. Se non trova, prova ricerca per primi caratteri
    if len(wine_name) >= 4:
        short_search = wine_name[:4].lower()
        matching_wines = await async_db_manager.search_wines(telegram_id, short_search, limit=limit)
        if matching_wines:
            logger.info(f"[FUZZY_MATCH] Trovato match con primi caratteri '{short_search}' per '{wine_name}'")
            return matching_wines
    
    # 3. Se ancora non trova, usa rapidfuzz per fuzzy matching su tutti i vini
    try:
        from rapidfuzz import fuzz, process
        all_wines = await async_db_manager.get_user_wines(telegram_id)
        
        if all_wines:
            wine_names = [w.name for w in all_wines]
            best_match = process.extractOne(
                wine_name,
                wine_names,
                scorer=fuzz.WRatio,  # Weighted Ratio (migliore per typo)
                score_cutoff=70  # Minimo 70% di similarità
            )
            
            if best_match:
                matched_name, score, _ = best_match
                logger.info(
                    f"[FUZZY_MATCH] Rapidfuzz match: '{wine_name}' → '{matched_name}' "
                    f"(similarità: {score:.1f}%)"
                )
                # Trova il vino corrispondente
                matching_wines = [w for w in all_wines if w.name == matched_name]
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
