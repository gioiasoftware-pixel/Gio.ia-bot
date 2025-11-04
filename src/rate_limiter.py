"""
Rate limiter per telegram-ai-bot usando PostgreSQL
"""
import logging
from typing import Tuple, Optional
from datetime import datetime, timedelta
from .database_async import get_async_session

logger = logging.getLogger(__name__)


async def check_rate_limit(
    telegram_id: int,
    action_type: str,
    max_requests: int = 20,
    window_seconds: int = 60
) -> Tuple[bool, Optional[int]]:
    """
    Verifica se l'utente può eseguire l'azione (rate limiting).
    
    Args:
        telegram_id: ID Telegram dell'utente
        action_type: Tipo azione ('message', 'command', ecc.)
        max_requests: Numero massimo richieste
        window_seconds: Finestra temporale in secondi
    
    Returns:
        Tuple (allowed: bool, retry_after: Optional[int])
        - allowed: True se permesso, False se rate limitato
        - retry_after: Secondi da attendere se rate limitato, None altrimenti
    """
    try:
        async with await get_async_session() as session:
            from sqlalchemy import text as sql_text
            
            # Crea tabella se non esiste (auto-migration)
            try:
                # Prima verifica se la tabella esiste
                check_table_query = sql_text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'rate_limit_logs'
                    )
                """)
                result = await session.execute(check_table_query)
                table_exists = result.scalar()
                
                if not table_exists:
                    # Crea tabella
                    create_table_query = sql_text("""
                        CREATE TABLE rate_limit_logs (
                            id SERIAL PRIMARY KEY,
                            telegram_id BIGINT NOT NULL,
                            action_type TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    await session.execute(create_table_query)
                    
                    # Crea indice
                    create_index_query = sql_text("""
                        CREATE INDEX idx_rate_limit_user_action 
                        ON rate_limit_logs (telegram_id, action_type, created_at)
                    """)
                    await session.execute(create_index_query)
                    await session.commit()
                else:
                    # Verifica se la colonna action_type esiste
                    check_column_query = sql_text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns 
                            WHERE table_name = 'rate_limit_logs' 
                            AND column_name = 'action_type'
                        )
                    """)
                    result = await session.execute(check_column_query)
                    column_exists = result.scalar()
                    
                    if not column_exists:
                        # Aggiungi colonna action_type
                        alter_table_query = sql_text("""
                            ALTER TABLE rate_limit_logs 
                            ADD COLUMN action_type TEXT NOT NULL DEFAULT 'message'
                        """)
                        await session.execute(alter_table_query)
                        await session.commit()
            except Exception as create_error:
                # Se fallisce, passa (fail open)
                logger.warning(f"[RATE_LIMIT] Impossibile creare/aggiornare tabella: {create_error}")
            
            # Calcola timestamp finestra
            window_start = datetime.utcnow() - timedelta(seconds=window_seconds)
            
            # Conta richieste nella finestra
            try:
                count_query = sql_text("""
                    SELECT COUNT(*) as count
                    FROM rate_limit_logs
                    WHERE telegram_id = :telegram_id
                      AND action_type = :action_type
                      AND created_at >= :window_start
                """)
                
                result = await session.execute(
                    count_query,
                    {
                        "telegram_id": telegram_id,
                        "action_type": action_type,
                        "window_start": window_start
                    }
                )
                row = result.fetchone()
                count = row[0] if row else 0
            except Exception as count_error:
                # Se tabella non esiste, permettere (fail open)
                logger.warning(f"[RATE_LIMIT] Errore conteggio: {count_error}")
                return True, None
            
            # Se superato limite, calcola retry_after
            if count >= max_requests:
                # Trova la richiesta più vecchia nella finestra
                oldest_query = sql_text("""
                    SELECT MIN(created_at) as oldest
                    FROM rate_limit_logs
                    WHERE telegram_id = :telegram_id
                      AND action_type = :action_type
                      AND created_at >= :window_start
                """)
                
                result = await session.execute(
                    oldest_query,
                    {
                        "telegram_id": telegram_id,
                        "action_type": action_type,
                        "window_start": window_start
                    }
                )
                row = result.fetchone()
                oldest = row[0] if row and row[0] else window_start
                
                # Calcola quando la finestra sarà libera
                window_end = oldest + timedelta(seconds=window_seconds)
                retry_after = int((window_end - datetime.utcnow()).total_seconds())
                retry_after = max(1, retry_after)  # Almeno 1 secondo
                
                logger.warning(
                    f"[RATE_LIMIT] Utente {telegram_id} rate limitato: "
                    f"{count}/{max_requests} in {window_seconds}s, retry_after={retry_after}s"
                )
                return False, retry_after
            
            # Registra questa richiesta
            insert_query = sql_text("""
                INSERT INTO rate_limit_logs (telegram_id, action_type, created_at)
                VALUES (:telegram_id, :action_type, :created_at)
            """)
            
            await session.execute(
                insert_query,
                {
                    "telegram_id": telegram_id,
                    "action_type": action_type,
                    "created_at": datetime.utcnow()
                }
            )
            
            # Pulisci vecchie entries (più vecchie di window_seconds * 2)
            cleanup_query = sql_text("""
                DELETE FROM rate_limit_logs
                WHERE created_at < :cleanup_before
            """)
            
            cleanup_before = datetime.utcnow() - timedelta(seconds=window_seconds * 2)
            await session.execute(
                cleanup_query,
                {"cleanup_before": cleanup_before}
            )
            
            await session.commit()
            
            return True, None
            
    except Exception as e:
        # In caso di errore, permettere la richiesta (fail open)
        logger.error(
            f"[RATE_LIMIT] Errore durante verifica rate limit: {e}",
            exc_info=True
        )
        return True, None

