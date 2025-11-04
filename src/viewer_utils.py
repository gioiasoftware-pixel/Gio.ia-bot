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


def generate_viewer_token(telegram_id: int, business_name: str) -> Optional[str]:
    """
    Genera token JWT temporaneo per viewer.
    
    Args:
        telegram_id: ID Telegram dell'utente
        business_name: Nome del locale
        
    Returns:
        Token JWT come stringa o None se errore
    """
    try:
        now = int(time.time())
        expiry = now + (TOKEN_EXPIRY_HOURS * 3600)  # 1 ora
        
        payload = {
            "telegram_id": telegram_id,
            "business_name": business_name,
            "iat": now,
            "exp": expiry
        }
        
        token = jwt.encode(
            payload,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        
        logger.info(f"Token JWT generato per {telegram_id}/{business_name}, scadenza: {TOKEN_EXPIRY_HOURS}h")
        return token
        
    except Exception as e:
        logger.error(f"Errore generazione token JWT: {e}")
        return None


def get_viewer_url(token: str) -> str:
    """
    Genera URL completo del viewer con token.
    
    Args:
        token: Token JWT
        
    Returns:
        URL completo del viewer
    """
    viewer_url = os.getenv("VIEWER_URL", "https://vineinventory-viewer.railway.app")
    return f"{viewer_url}?token={token}"

