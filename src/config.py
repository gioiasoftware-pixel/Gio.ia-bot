import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Carica variabili ambiente
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
BOT_MODE = os.getenv("BOT_MODE", "polling")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

def validate_config():
    """Valida le configurazioni critiche all'avvio."""
    errors = []
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN non configurato")
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY non configurato")
    
    if BOT_MODE == "webhook" and not WEBHOOK_URL:
        errors.append("WEBHOOK_URL richiesta in modalità webhook")
    
    if errors:
        error_msg = "❌ Configurazione mancante:\n" + "\n".join(f"  - {error}" for error in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("✅ Configurazione validata con successo")
    return True



