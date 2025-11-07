"""
Structured logging con correlation ID per telegram-ai-bot
"""
import logging
import uuid
import contextvars
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Context variables per tracciare richieste
_request_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar('request_context', default={})


def set_request_context(telegram_id: int, correlation_id: Optional[str] = None):
    """
    Imposta contesto richiesta per logging strutturato.
    
    Args:
        telegram_id: ID Telegram dell'utente
        correlation_id: ID correlazione (genera se None)
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    
    _request_context.set({
        "telegram_id": telegram_id,
        "correlation_id": correlation_id
    })


def get_request_context() -> Dict[str, Any]:
    """
    Recupera contesto richiesta corrente.
    
    Returns:
        Dict con telegram_id e correlation_id
    """
    return _request_context.get({})


def get_correlation_id(context=None) -> Optional[str]:
    """
    Recupera correlation ID dal contesto.
    
    Args:
        context: Context Telegram (opzionale, per compatibilità)
    
    Returns:
        Correlation ID se disponibile, None altrimenti
    """
    ctx = get_request_context()
    return ctx.get("correlation_id")


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **extra
):
    """
    Log con contesto strutturato (telegram_id, correlation_id).
    
    Args:
        level: 'info', 'warning', 'error', 'debug'
        message: Messaggio da loggare
        telegram_id: ID Telegram (usa contesto se None)
        correlation_id: ID correlazione (usa contesto se None)
        **extra: Campi aggiuntivi per log
    """
    # Recupera contesto se non fornito
    ctx = get_request_context()
    if telegram_id is None:
        telegram_id = ctx.get("telegram_id")
    if correlation_id is None:
        correlation_id = ctx.get("correlation_id")
    
    # Formatta messaggio con contesto
    log_message = message
    if telegram_id:
        log_message = f"[telegram_id={telegram_id}] {log_message}"
    if correlation_id:
        log_message = f"[correlation_id={correlation_id}] {log_message}"
    
    # Log con livello appropriato
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(log_message, **extra)






