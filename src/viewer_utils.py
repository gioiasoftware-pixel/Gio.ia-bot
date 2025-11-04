"""
Utility per generazione token JWT per viewer
"""
import jwt
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Secret key condivisa con processor (da variabile ambiente)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-secret-key-2025")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 1  # Token valido per 1 ora


def generate_viewer_token(telegram_id: int, business_name: str, correlation_id: Optional[str] = None) -> Optional[str]:
    """
    Genera token JWT temporaneo per viewer.
    
    Args:
        telegram_id: ID Telegram dell'utente
        business_name: Nome del locale
        correlation_id: ID correlazione per logging (opzionale)
        
    Returns:
        Token JWT come stringa o None se errore
    """
    try:
        logger.info(
            f"[VIEWER_TOKEN] Inizio generazione token per telegram_id={telegram_id}, "
            f"business_name={business_name}, correlation_id={correlation_id}"
        )
        
        # Verifica configurazione
        if not JWT_SECRET_KEY or JWT_SECRET_KEY == "change-me-in-production-secret-key-2025":
            logger.warning(f"[VIEWER_TOKEN] JWT_SECRET_KEY non configurata o default!")
        
        now = int(time.time())
        expiry = now + (TOKEN_EXPIRY_HOURS * 3600)  # 1 ora
        
        payload = {
            "telegram_id": telegram_id,
            "business_name": business_name,
            "iat": now,
            "exp": expiry
        }
        
        logger.debug(
            f"[VIEWER_TOKEN] Payload token: telegram_id={telegram_id}, "
            f"business_name={business_name}, iat={now}, exp={expiry}"
        )
        
        token = jwt.encode(
            payload,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        
        logger.info(
            f"[VIEWER_TOKEN] Token JWT generato con successo per {telegram_id}/{business_name}, "
            f"scadenza={TOKEN_EXPIRY_HOURS}h, correlation_id={correlation_id}, "
            f"token_length={len(token)}"
        )
        
        return token
        
    except jwt.PyJWTError as e:
        logger.error(
            f"[VIEWER_TOKEN] Errore PyJWT durante generazione token: {e}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}"
        )
        return None
    except Exception as e:
        logger.error(
            f"[VIEWER_TOKEN] Errore generico generazione token JWT: {e}, "
            f"telegram_id={telegram_id}, correlation_id={correlation_id}",
            exc_info=True
        )
        return None


def get_viewer_url(token: str, correlation_id: Optional[str] = None) -> str:
    """
    Genera URL completo del viewer con token.
    
    Args:
        token: Token JWT
        correlation_id: ID correlazione per logging (opzionale)
        
    Returns:
        URL completo del viewer
    """
    viewer_url = os.getenv("VIEWER_URL", "https://vineinventory-viewer.railway.app")
    
    if not viewer_url:
        logger.warning(f"[VIEWER_URL] VIEWER_URL non configurata, uso default")
        viewer_url = "https://vineinventory-viewer.railway.app"
    
    full_url = f"{viewer_url}?token={token}"
    
    logger.info(
        f"[VIEWER_URL] URL generato: viewer_url={viewer_url}, "
        f"token_length={len(token)}, correlation_id={correlation_id}, "
        f"full_url_length={len(full_url)}"
    )
    
    return full_url



