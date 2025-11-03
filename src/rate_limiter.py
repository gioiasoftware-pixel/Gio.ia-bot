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
            # Conta richieste ultima finestra
            query = sql_text("""
                SELECT COUNT(*) 
                FROM rate_limit_logs
                WHERE key = :key 
                AND created_at >= to_timestamp(:window_start)
            """)
            result = await session.execute(query, {
                "key": key,
                "window_start": window_start
            })
            count = result.scalar_one()
            
            if count >= max_requests:
                # Calcola retry_after (quando scade finestra più vecchia)
                oldest_query = sql_text("""
                    SELECT MIN(created_at) 
                    FROM rate_limit_logs
                    WHERE key = :key
                    AND created_at >= to_timestamp(:window_start)
                """)
                oldest_result = await session.execute(oldest_query, {
                    "key": key,
                    "window_start": window_start
                })
                oldest_timestamp = oldest_result.scalar_one()
                
                if oldest_timestamp:
                    retry_after = int((oldest_timestamp.timestamp() + window_seconds) - now)
                    retry_after = max(1, retry_after)  # Min 1 secondo
                else:
                    retry_after = window_seconds
                
                return (False, retry_after)
            
            # Registra richiesta (inserisci o ignora se tabella non esiste)
            try:
                insert_query = sql_text("""
                    INSERT INTO rate_limit_logs (key, created_at)
                    VALUES (:key, to_timestamp(:now))
                """)
                await session.execute(insert_query, {"key": key, "now": now})
                await session.commit()
            except Exception as e:
                # Tabella non esiste o errore - log ma non bloccare
                logger.warning(f"Error inserting rate limit log (table may not exist): {e}")
                await session.rollback()
            
            return (True, None)
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # In caso di errore, permettere la richiesta (fail open)
            return (True, None)




