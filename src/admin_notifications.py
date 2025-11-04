"""
Gestione notifiche admin per telegram-ai-bot
"""
import json
import logging
from typing import Dict, Any, Optional
from .database_async import get_async_session

logger = logging.getLogger(__name__)


async def enqueue_admin_notification(
    event_type: str,
    telegram_id: int,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> bool:
    """
    Accoda una notifica admin nella tabella admin_notifications.
    
    Args:
        event_type: Tipo evento ('onboarding_completed', 'inventory_uploaded', 'error', ecc.)
        telegram_id: ID Telegram dell'utente
        payload: Dizionario con dettagli evento (business_name, error_message, ecc.)
        correlation_id: ID correlazione per debugging (opzionale)
    
    Returns:
        True se inserita con successo, False altrimenti
    """
    try:
        # Serializza payload in JSON
        payload_json = json.dumps(payload)
        
        # Inserisci nella tabella admin_notifications
        async with await get_async_session() as session:
            # Usa SQLAlchemy per inserire
            from sqlalchemy import text as sql_text
            
            query = sql_text("""
                INSERT INTO admin_notifications 
                (event_type, telegram_id, correlation_id, payload, status)
                VALUES (:event_type, :telegram_id, :correlation_id, :payload::jsonb, 'pending')
            """)
            
            await session.execute(
                query,
                {
                    "event_type": event_type,
                    "telegram_id": telegram_id,
                    "correlation_id": correlation_id,
                    "payload": payload_json
                }
            )
            await session.commit()
        
        logger.info(
            f"[ADMIN_NOTIF] Notifica accodata: event_type={event_type}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}"
        )
        return True
        
    except Exception as e:
        logger.error(
            f"[ADMIN_NOTIF] Errore durante accodamento notifica: {e}",
            exc_info=True
        )
        return False

