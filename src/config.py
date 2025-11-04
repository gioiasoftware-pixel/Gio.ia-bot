import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Carica variabili ambiente
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
BOT_MODE = os.getenv("BOT_MODE", "polling")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

# Database PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")

# Processor Microservice
PROCESSOR_URL = os.getenv("PROCESSOR_URL", "https://gioia-processor-production.up.railway.app")

# Viewer Microservice
VIEWER_URL = os.getenv("VIEWER_URL", "https://vineinventory-viewer-production.up.railway.app")

def validate_config():
    """Valida le configurazioni critiche all'avvio."""
    errors = []
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN non configurato")
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY non configurato")
    
    if not DATABASE_URL:
        errors.append("DATABASE_URL non configurato (PostgreSQL)")
    
    if BOT_MODE == "webhook" and not WEBHOOK_URL:
        errors.append("WEBHOOK_URL richiesta in modalità webhook")
    
    # Processor URL è opzionale (default localhost)
    if not PROCESSOR_URL:
        logger.warning("PROCESSOR_URL non configurato, usando localhost:8001")
    
    if errors:
        error_msg = "❌ Configurazione mancante:\n" + "\n".join(f"  - {error}" for error in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Log URLs per debug
    logger.info(f"🔗 Processor URL: {PROCESSOR_URL}")
    logger.info(f"🔗 Viewer URL: {VIEWER_URL}")
    logger.info("✅ Configurazione validata con successo")
    return True