"""
Modulo per notifiche admin (opzionale - fallback se non disponibile)
"""
import logging
import httpx
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# URL del processor per notifiche admin (opzionale)
PROCESSOR_URL = os.getenv("PROCESSOR_URL", "https://gioia-processor-production.up.railway.app")
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

