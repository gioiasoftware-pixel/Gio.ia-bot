"""
Gestione lock/mutex per serializzare operazioni per utente.
"""
import asyncio
import logging
from typing import Dict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Dizionario per mantenere lock per utente
_user_locks: Dict[int, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


async def _get_user_lock(telegram_id: int) -> asyncio.Lock:
    """Ottiene o crea lock per un utente specifico."""
    async with _locks_lock:
        if telegram_id not in _user_locks:
            _user_locks[telegram_id] = asyncio.Lock()
        return _user_locks[telegram_id]


@asynccontextmanager
async def user_mutex(telegram_id: int, timeout_seconds: int = 300, block_timeout: int = 10):
    """
    Context manager per serializzare operazioni per utente.
    
    Args:
        telegram_id: ID Telegram dell'utente
        timeout_seconds: Timeout totale per l'operazione (default 300s = 5min)
        block_timeout: Timeout per acquisire il lock (default 10s)
    
    Yields:
        Lock acquisito per l'utente
    
    Raises:
        asyncio.TimeoutError: Se il lock non può essere acquisito entro block_timeout
    """
    lock = await _get_user_lock(telegram_id)
    
    try:
        # Prova ad acquisire il lock con timeout
        await asyncio.wait_for(lock.acquire(), timeout=block_timeout)
        logger.debug(f"Lock acquisito per utente {telegram_id}")
        
        try:
            yield lock
        finally:
            lock.release()
            logger.debug(f"Lock rilasciato per utente {telegram_id}")
            
    except asyncio.TimeoutError:
        logger.warning(
            f"Timeout acquisizione lock per utente {telegram_id} "
            f"(timeout: {block_timeout}s)"
        )
        raise




