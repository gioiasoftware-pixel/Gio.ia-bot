"""
Modulo per notifiche admin (opzionale - fallback se non disponibile)
"""
import logging
import httpx
import os
import traceback
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# URL del processor per notifiche admin (opzionale)
def _normalize_url(url: str) -> str:
    """Normalizza URL aggiungendo https:// se manca il protocollo"""
    if not url:
        return "https://gioia-processor-production.up.railway.app"
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url

PROCESSOR_URL_RAW = os.getenv("PROCESSOR_URL", "https://gioia-processor-production.up.railway.app")
PROCESSOR_URL = _normalize_url(PROCESSOR_URL_RAW)
ADMIN_NOTIFICATIONS_ENABLED = os.getenv("ADMIN_NOTIFICATIONS_ENABLED", "false").lower() == "true"


async def enqueue_admin_notification(
    event_type: str,
    telegram_id: int,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> bool:
    """
    Accoda notifica admin (fallback semplice se admin bot non disponibile).
    
    Args:
        event_type: Tipo evento (es. "onboarding_completed", "error")
        telegram_id: ID Telegram utente
        payload: Dati evento
        correlation_id: ID correlazione (opzionale)
    
    Returns:
        True se notifica accodata, False altrimenti
    """
    if not ADMIN_NOTIFICATIONS_ENABLED:
        logger.debug(f"[ADMIN_NOTIF] Notifiche admin disabilitate, evento {event_type} ignorato")
        return False
    
    try:
        # Prova a inviare notifica al processor (se endpoint disponibile)
        url = f"{PROCESSOR_URL.rstrip('/')}/admin/notifications"
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url,
                json={
                    "event_type": event_type,
                    "telegram_id": telegram_id,
                    "payload": payload,
                    "correlation_id": correlation_id
                }
            )
            response.raise_for_status()
            logger.info(f"[ADMIN_NOTIF] Notifica admin inviata: {event_type} per utente {telegram_id}")
            return True
    except Exception as e:
        # Fallback silenzioso - non bloccare il flusso principale
        logger.debug(f"[ADMIN_NOTIF] Impossibile inviare notifica admin: {e}")
        return False


async def log_error_and_notify_admin(
    message: str,
    telegram_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
    component: str = "telegram-ai-bot",
    error_type: str = "error",
    exc_info: bool = False,
    **extra_context
) -> None:
    """
    Logga errore e invia automaticamente notifica admin.
    
    Args:
        message: Messaggio errore
        telegram_id: ID Telegram utente (opzionale)
        correlation_id: ID correlazione (opzionale, usa get_correlation_id se None)
        component: Componente che ha generato l'errore (default: "telegram-ai-bot")
        error_type: Tipo errore per categorizzazione (default: "error")
        exc_info: Se True, include traceback nel log
        **extra_context: Contesto aggiuntivo per la notifica
    """
    # Logga sempre l'errore
    if exc_info:
        logger.error(message, exc_info=True)
    else:
        logger.error(message)
    
    # Invia notifica admin (async, non blocca)
    try:
        error_details = {
            "error_message": str(message),
            "component": component,
            "error_type": error_type,
            **extra_context
        }
        
        # Se exc_info, aggiungi traceback
        if exc_info:
            error_details["traceback"] = traceback.format_exc()
        
        # Recupera correlation_id se non fornito
        if correlation_id is None:
            try:
                from .structured_logging import get_correlation_id
                correlation_id = get_correlation_id()
            except ImportError:
                pass
        
        # Chiama enqueue_admin_notification
        await enqueue_admin_notification(
            event_type="error",
            telegram_id=telegram_id or 0,
            payload=error_details,
            correlation_id=correlation_id
        )
    except Exception as notif_error:
        # Se fallisce la notifica, logga ma non bloccare
        logger.warning(f"[ADMIN_NOTIF] Errore invio notifica admin per errore: {notif_error}", exc_info=True)

