import logging
from openai import OpenAI, OpenAIError
from .config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)


def get_ai_response(prompt: str) -> str:
    """Genera risposta AI con gestione errori robusta."""
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key non configurata")
        return "⚠️ L'AI non è configurata. Contatta l'amministratore."
    
    if not prompt or not prompt.strip():
        logger.warning("Prompt vuoto ricevuto")
        return "⚠️ Messaggio vuoto ricevuto. Prova a scrivere qualcosa!"
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario. Sei gentile, professionale e parli in italiano. Aiuti gli utenti con domande su inventario, movimenti di magazzino e report."},
                {"role": "user", "content": prompt.strip()},
            ],
            max_tokens=1000,
            temperature=0.7,
            timeout=30
        )
        
        if not response.choices or not response.choices[0].message.content:
            logger.error("Risposta vuota da OpenAI")
            return "⚠️ Errore nella generazione della risposta. Riprova."
            
        return response.choices[0].message.content.strip()
        
    except OpenAIError as e:
        logger.error(f"Errore OpenAI: {e}")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
    except Exception as e:
        logger.error(f"Errore imprevisto in get_ai_response: {e}")
        return "⚠️ Errore interno. Contatta l'amministratore."



