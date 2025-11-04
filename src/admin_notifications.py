"""
Helper per scrivere notifiche admin nella tabella admin_notifications
"""
import os
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import asyncpg

logger = logging.getLogger(__name__)

# Pool condiviso per admin_notifications
_admin_pool: Optional[asyncpg.Pool] = None


async def _get_admin_pool() -> Optional[asyncpg.Pool]:
    """Ottieni pool database per admin_notifications (singleton)"""
    global _admin_pool
    
    if _admin_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning("DATABASE_URL non configurata, admin_notifications disabilitate")
            return None
        
        # Normalizza DATABASE_URL per asyncpg
        if database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        try:
            _admin_pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
            logger.info("✅ Pool admin_notifications creato")
        except Exception as e:
            logger.error(f"Errore creazione pool admin_notifications: {e}")
            return None
    
    return _admin_pool


async def enqueue_admin_notification(
    event_type: str,
    telegram_id: int,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> bool:
    """
    Inserisce una notifica nella tabella admin_notifications.
    
    Args:
        event_type: Tipo evento ('onboarding_completed', 'inventory_uploaded', 'error')
        telegram_id: ID Telegram dell'utente
        payload: Dati dell'evento (dict)
        correlation_id: ID correlazione per tracciamento (opzionale)
    
    Returns:
        True se inserita con successo, False altrimenti
    """
    try:
        pool = await _get_admin_pool()
        if not pool:
            return False
        
        notification_id = str(uuid.uuid4())
        
        # Serializza payload come JSON string per asyncpg
        payload_json = json.dumps(payload) if isinstance(payload, dict) else payload
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO admin_notifications 
                (id, created_at, status, event_type, telegram_id, correlation_id, payload, retry_count, next_attempt_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            """,
                notification_id,
                datetime.utcnow(),
                'pending',
                event_type,
                telegram_id,
                correlation_id,
                payload_json,
                0,
                datetime.utcnow()
            )
        
        logger.info(f"Notifica admin inserita: {event_type} per utente {telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"Errore inserimento notifica admin: {e}")
        return False


async def close_admin_pool():
    """Chiudi pool database (utile per cleanup)"""
    global _admin_pool
    if _admin_pool:
        await _admin_pool.close()
        _admin_pool = None



"""
import os
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import asyncpg

logger = logging.getLogger(__name__)

# Pool condiviso per admin_notifications
_admin_pool: Optional[asyncpg.Pool] = None


async def _get_admin_pool() -> Optional[asyncpg.Pool]:
    """Ottieni pool database per admin_notifications (singleton)"""
    global _admin_pool
    
    if _admin_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning("DATABASE_URL non configurata, admin_notifications disabilitate")
            return None
        
        # Normalizza DATABASE_URL per asyncpg
        if database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        try:
            _admin_pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
            logger.info("✅ Pool admin_notifications creato")
        except Exception as e:
            logger.error(f"Errore creazione pool admin_notifications: {e}")
            return None
    
    return _admin_pool


async def enqueue_admin_notification(
    event_type: str,
    telegram_id: int,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None
) -> bool:
    """
    Inserisce una notifica nella tabella admin_notifications.
    
    Args:
        event_type: Tipo evento ('onboarding_completed', 'inventory_uploaded', 'error')
        telegram_id: ID Telegram dell'utente
        payload: Dati dell'evento (dict)
        correlation_id: ID correlazione per tracciamento (opzionale)
    
    Returns:
        True se inserita con successo, False altrimenti
    """
    try:
        pool = await _get_admin_pool()
        if not pool:
            return False
        
        notification_id = str(uuid.uuid4())
        
        # Serializza payload come JSON string per asyncpg
        payload_json = json.dumps(payload) if isinstance(payload, dict) else payload
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO admin_notifications 
                (id, created_at, status, event_type, telegram_id, correlation_id, payload, retry_count, next_attempt_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            """,
                notification_id,
                datetime.utcnow(),
                'pending',
                event_type,
                telegram_id,
                correlation_id,
                payload_json,
                0,
                datetime.utcnow()
            )
        
        logger.info(f"Notifica admin inserita: {event_type} per utente {telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"Errore inserimento notifica admin: {e}")
        return False


async def close_admin_pool():
    """Chiudi pool database (utile per cleanup)"""
    global _admin_pool
    if _admin_pool:
        await _admin_pool.close()
        _admin_pool = None


