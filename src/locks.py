"""
Lock per serializzare operazioni per utente usando Postgres advisory locks.
"""
import os
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text as sql_text
from .database_async import get_async_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def user_mutex(telegram_id: int, timeout_seconds: int = 60, block_timeout: int = 5):
    """
    Lock advisory Postgres per utente.
    
    Args:
        telegram_id: ID Telegram utente
        timeout_seconds: TTL lock (secondi) - non usato direttamente, lock rilasciato a fine transazione
        block_timeout: Tempo max attesa lock (secondi) - 0 = non bloccante
    
    Yields:
        None
    
    Raises:
        RuntimeError: Se lock non ottenuto entro block_timeout
    """
    async with await get_async_session() as session:
        # PostgreSQL advisory lock: usa hash deterministico di telegram_id
        # Usa modulo per mappare a bigint valido per pg_advisory_lock
        lock_key = abs(hash(f"user:{telegram_id}")) % (2**63)  # Bigint PostgreSQL
        
        try:
            if block_timeout > 0:
                # Usa pg_advisory_lock (bloccante) - aspetta fino a ottenere lock
                # PostgreSQL non ha timeout nativo, quindi usiamo try_lock in loop
                import asyncio
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    query = sql_text("SELECT pg_try_advisory_lock(:lock_key)")
                    result = await session.execute(query, {"lock_key": lock_key})
                    acquired = result.scalar_one()
                    
                    if acquired:
                        break
                    
                    # Controlla timeout
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= block_timeout:
                        raise RuntimeError(f"User {telegram_id} is busy (lock timeout after {block_timeout}s)")
                    
                    # Attendi prima di riprovare
                    await asyncio.sleep(0.1)
            else:
                # Usa pg_try_advisory_lock (non bloccante)
                query = sql_text("SELECT pg_try_advisory_lock(:lock_key)")
                result = await session.execute(query, {"lock_key": lock_key})
                acquired = result.scalar_one()
                
                if not acquired:
                    raise RuntimeError(f"User {telegram_id} is busy (lock already held)")
            
            await session.commit()
            
            try:
                yield
            finally:
                # Rilascia lock
                unlock_query = sql_text("SELECT pg_advisory_unlock(:lock_key)")
                await session.execute(unlock_query, {"lock_key": lock_key})
                await session.commit()
                
        except Exception as e:
            await session.rollback()
            if isinstance(e, RuntimeError):
                raise  # Re-raise "User is busy"
            logger.error(f"Error acquiring/releasing lock for user {telegram_id}: {e}")
            raise


