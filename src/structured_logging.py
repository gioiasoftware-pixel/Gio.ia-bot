"""
Structured logging con contesto per request tracking
"""
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Thread-local storage per contesto request
_context = threading.local()


def set_request_context(telegram_id: int, correlation_id: str):
    """
    Imposta contesto request per logging strutturato.
    """
    _context.telegram_id = telegram_id
    _context.correlation_id = correlation_id


def get_request_context() -> Dict[str, Any]:
    """
    Ottieni contesto request corrente.
    """
    return {
        "telegram_id": getattr(_context, 'telegram_id', None),
        "correlation_id": getattr(_context, 'correlation_id', None)
    }


def get_correlation_id(context) -> Optional[str]:
    """
    Ottieni correlation_id dal contesto request o user_data.
    """
    # Prova da thread-local context
    correlation_id = getattr(_context, 'correlation_id', None)
    if correlation_id:
        return correlation_id
    
    # Prova da user_data se disponibile
    if hasattr(context, 'user_data'):
        return context.user_data.get('correlation_id')
    
    return None


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **kwargs
):
    """
    Log con contesto strutturato.
    
    Args:
        level: Livello log ('info', 'warning', 'error', 'debug')
        message: Messaggio da loggare
        telegram_id: ID Telegram (opzionale, usa contesto se non fornito)
        correlation_id: ID correlazione (opzionale, usa contesto se non fornito)
        **kwargs: Campi aggiuntivi da includere nel log
    """
    # Usa contesto thread-local se disponibile
    ctx = get_request_context()
    final_telegram_id = telegram_id or ctx.get('telegram_id')
    final_correlation_id = correlation_id or ctx.get('correlation_id')
    
    # Costruisci messaggio strutturato
    parts = [message]
    if final_telegram_id:
        parts.append(f"[telegram_id={final_telegram_id}]")
    if final_correlation_id:
        parts.append(f"[correlation_id={final_correlation_id}]")
    
    # Aggiungi campi aggiuntivi
    if kwargs:
        extra_parts = [f"{k}={v}" for k, v in kwargs.items()]
        parts.extend(extra_parts)
    
    log_message = " ".join(parts)
    
    # Logga al livello appropriato
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(log_message)
