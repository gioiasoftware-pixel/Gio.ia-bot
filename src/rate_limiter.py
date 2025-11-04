"""
Rate limiter semplice usando Postgres (alternativa a Redis).
"""
import os
import time
import logging
from typing import Tuple, Optional
from sqlalchemy import text as sql_text
from .database_async import get_async_session

logger = logging.getLogger(__name__)


async def check_rate_limit(
    telegram_id: int,
    action: str,
    max_requests: int = 10,
    window_seconds: int = 60
) -> Tuple[bool, Optional[int]]:
    """
    Verifica rate limit per utente/azione.
    
    Args:
        telegram_id: ID Telegram utente
        action: Tipo azione ('message', 'upload', 'movement')
        max_requests: Max richieste per finestra
        window_seconds: Durata finestra (secondi)
    
    Returns:
        (allowed: bool, retry_after: Optional[int])
        retry_after = secondi da attendere se rate limited
    """
    async with await get_async_session() as session:
        key = f"ratelimit:{telegram_id}:{action}"
        now = int(time.time())
        window_start = now - window_seconds
        
        try:
            # Nuovo schema: tabella rate_limits (telegram_id, action, timestamp)
            count_query = sql_text("""
                SELECT COUNT(*)
                FROM rate_limits
                WHERE telegram_id = :telegram_id
                  AND action = :action
                  AND timestamp >= to_timestamp(:window_start)
            """)
            result = await session.execute(count_query, {
                "telegram_id": telegram_id,
                "action": action,
                "window_start": window_seconds and window_start or 0
            })
            count = result.scalar_one()

            if count >= max_requests:
                # Calcola retry_after basandosi sul record più vecchio nella finestra
                oldest_query = sql_text("""
                    SELECT MIN(timestamp)
                    FROM rate_limits
                    WHERE telegram_id = :telegram_id
                      AND action = :action
                      AND timestamp >= to_timestamp(:window_start)
                """)
                oldest_result = await session.execute(oldest_query, {
                    "telegram_id": telegram_id,
                    "action": action,
                    "window_start": window_seconds and window_start or 0
                })
                oldest_timestamp = oldest_result.scalar_one()

                if oldest_timestamp:
                    retry_after = int((oldest_timestamp.timestamp() + window_seconds) - now)
                    retry_after = max(1, retry_after)
                else:
                    retry_after = window_seconds
                return (False, retry_after)

            # Registra nuova richiesta
            try:
                insert_query = sql_text("""
                    INSERT INTO rate_limits (telegram_id, action, timestamp)
                    VALUES (:telegram_id, :action, to_timestamp(:now))
                """)
                await session.execute(insert_query, {
                    "telegram_id": telegram_id,
                    "action": action,
                    "now": now
                })
                await session.commit()
            except Exception as e:
                logger.warning(f"Error inserting rate limit record: {e}")
                await session.rollback()

            return (True, None)
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # In caso di errore, permettere la richiesta (fail open)
            return (True, None)





"""
import os
import time
import logging
from typing import Tuple, Optional
from sqlalchemy import text as sql_text
from .database_async import get_async_session

logger = logging.getLogger(__name__)


async def check_rate_limit(
    telegram_id: int,
    action: str,
    max_requests: int = 10,
    window_seconds: int = 60
) -> Tuple[bool, Optional[int]]:
    """
    Verifica rate limit per utente/azione.
    
    Args:
        telegram_id: ID Telegram utente
        action: Tipo azione ('message', 'upload', 'movement')
        max_requests: Max richieste per finestra
        window_seconds: Durata finestra (secondi)
    
    Returns:
        (allowed: bool, retry_after: Optional[int])
        retry_after = secondi da attendere se rate limited
    """
    async with await get_async_session() as session:
        key = f"ratelimit:{telegram_id}:{action}"
        now = int(time.time())
        window_start = now - window_seconds
        
        try:
            # Nuovo schema: tabella rate_limits (telegram_id, action, timestamp)
            count_query = sql_text("""
                SELECT COUNT(*)
                FROM rate_limits
                WHERE telegram_id = :telegram_id
                  AND action = :action
                  AND timestamp >= to_timestamp(:window_start)
            """)
            result = await session.execute(count_query, {
                "telegram_id": telegram_id,
                "action": action,
                "window_start": window_seconds and window_start or 0
            })
            count = result.scalar_one()

            if count >= max_requests:
                # Calcola retry_after basandosi sul record più vecchio nella finestra
                oldest_query = sql_text("""
                    SELECT MIN(timestamp)
                    FROM rate_limits
                    WHERE telegram_id = :telegram_id
                      AND action = :action
                      AND timestamp >= to_timestamp(:window_start)
                """)
                oldest_result = await session.execute(oldest_query, {
                    "telegram_id": telegram_id,
                    "action": action,
                    "window_start": window_seconds and window_start or 0
                })
                oldest_timestamp = oldest_result.scalar_one()

                if oldest_timestamp:
                    retry_after = int((oldest_timestamp.timestamp() + window_seconds) - now)
                    retry_after = max(1, retry_after)
                else:
                    retry_after = window_seconds
                return (False, retry_after)

            # Registra nuova richiesta
            try:
                insert_query = sql_text("""
                    INSERT INTO rate_limits (telegram_id, action, timestamp)
                    VALUES (:telegram_id, :action, to_timestamp(:now))
                """)
                await session.execute(insert_query, {
                    "telegram_id": telegram_id,
                    "action": action,
                    "now": now
                })
                await session.commit()
            except Exception as e:
                logger.warning(f"Error inserting rate limit record: {e}")
                await session.rollback()

            return (True, None)
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # In caso di errore, permettere la richiesta (fail open)
            return (True, None)




