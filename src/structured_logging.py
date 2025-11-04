"""
Logging strutturato con telegram_id e correlation_id per tracciamento end-to-end.
"""
import json
import logging
import uuid
from typing import Optional
import contextvars

logger = logging.getLogger("app")

# Context vars per tracciamento request
_current_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('correlation_id', default=None)
_current_telegram_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('telegram_id', default=None)


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **extra
):
    """
    Log strutturato JSON con contesto utente.
    
    Args:
        level: 'info', 'warning', 'error', 'debug'
        message: Messaggio log
        telegram_id: ID Telegram utente (usa context se None)
        correlation_id: ID correlazione request (usa context se None)
        **extra: Campi aggiuntivi per log
    """
    # Usa context se telegram_id/correlation_id non forniti
    if telegram_id is None:
        try:
            telegram_id = _current_telegram_id.get()
        except LookupError:
            telegram_id = None
    
    if correlation_id is None:
        try:
            correlation_id = _current_correlation_id.get()
        except LookupError:
            correlation_id = str(uuid.uuid4())
    
    payload = {
        "level": level.upper(),
        "message": message,
        "telegram_id": telegram_id,
        "correlation_id": correlation_id,
        **extra
    }
    
    # Log come JSON per parsing strutturato
    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        json.dumps(payload)
    )


def set_request_context(telegram_id: int, correlation_id: Optional[str] = None):
    """Imposta contesto request corrente"""
    _current_telegram_id.set(telegram_id)
    _current_correlation_id.set(correlation_id or str(uuid.uuid4()))


def get_request_context() -> dict:
    """Ottieni contesto request corrente"""
    try:
        return {
            "telegram_id": _current_telegram_id.get(None),
            "correlation_id": _current_correlation_id.get(None)
        }
    except LookupError:
        return {"telegram_id": None, "correlation_id": None}


def get_correlation_id(context_or_var=None) -> Optional[str]:
    """
    Ottieni correlation_id dal context o dalle context vars.
    
    Args:
        context_or_var: Context Telegram (opzionale) o None per usare context vars
    
    Returns:
        correlation_id come stringa o None
    """
    try:
        if context_or_var and hasattr(context_or_var, 'user_data'):
            # Prova a leggere dal context Telegram
            correlation_id = context_or_var.user_data.get('correlation_id')
            if correlation_id:
                return correlation_id
        
        # Prova a leggere dalle context vars
        return _current_correlation_id.get()
    except (LookupError, AttributeError):
        return None





"""
import json
import logging
import uuid
from typing import Optional
import contextvars

logger = logging.getLogger("app")

# Context vars per tracciamento request
_current_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('correlation_id', default=None)
_current_telegram_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('telegram_id', default=None)


def log_with_context(
    level: str,
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    **extra
):
    """
    Log strutturato JSON con contesto utente.
    
    Args:
        level: 'info', 'warning', 'error', 'debug'
        message: Messaggio log
        telegram_id: ID Telegram utente (usa context se None)
        correlation_id: ID correlazione request (usa context se None)
        **extra: Campi aggiuntivi per log
    """
    # Usa context se telegram_id/correlation_id non forniti
    if telegram_id is None:
        try:
            telegram_id = _current_telegram_id.get()
        except LookupError:
            telegram_id = None
    
    if correlation_id is None:
        try:
            correlation_id = _current_correlation_id.get()
        except LookupError:
            correlation_id = str(uuid.uuid4())
    
    payload = {
        "level": level.upper(),
        "message": message,
        "telegram_id": telegram_id,
        "correlation_id": correlation_id,
        **extra
    }
    
    # Log come JSON per parsing strutturato
    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        json.dumps(payload)
    )


def set_request_context(telegram_id: int, correlation_id: Optional[str] = None):
    """Imposta contesto request corrente"""
    _current_telegram_id.set(telegram_id)
    _current_correlation_id.set(correlation_id or str(uuid.uuid4()))


def get_request_context() -> dict:
    """Ottieni contesto request corrente"""
    try:
        return {
            "telegram_id": _current_telegram_id.get(None),
            "correlation_id": _current_correlation_id.get(None)
        }
    except LookupError:
        return {"telegram_id": None, "correlation_id": None}


def get_correlation_id(context_or_var=None) -> Optional[str]:
    """
    Ottieni correlation_id dal context o dalle context vars.
    
    Args:
        context_or_var: Context Telegram (opzionale) o None per usare context vars
    
    Returns:
        correlation_id come stringa o None
    """
    try:
        if context_or_var and hasattr(context_or_var, 'user_data'):
            # Prova a leggere dal context Telegram
            correlation_id = context_or_var.user_data.get('correlation_id')
            if correlation_id:
                return correlation_id
        
        # Prova a leggere dalle context vars
        return _current_correlation_id.get()
    except (LookupError, AttributeError):
        return None




