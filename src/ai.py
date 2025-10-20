import logging
from openai import OpenAI, OpenAIError
from .config import OPENAI_API_KEY, OPENAI_MODEL
from .database import db_manager
from .inventory import inventory_manager

logger = logging.getLogger(__name__)


def get_ai_response(prompt: str, telegram_id: int = None) -> str:
    """Genera risposta AI con accesso ai dati utente."""
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key non configurata")
        return "⚠️ L'AI non è configurata. Contatta l'amministratore."
    
    if not prompt or not prompt.strip():
        logger.warning("Prompt vuoto ricevuto")
        return "⚠️ Messaggio vuoto ricevuto. Prova a scrivere qualcosa!"
    
    try:
        # Prepara il contesto utente se disponibile
        user_context = ""
        if telegram_id:
            user = db_manager.get_user_by_telegram_id(telegram_id)
            if user:
                # Aggiungi informazioni utente
                user_context = f"""
INFORMAZIONI UTENTE:
- Nome attività: {user.business_name or 'Non specificato'}
- Tipo attività: {user.business_type or 'Non specificato'}
- Località: {user.location or 'Non specificata'}
- Onboarding completato: {'Sì' if user.onboarding_completed else 'No'}

INVENTARIO ATTUALE:
"""
                # Aggiungi riassunto inventario
                inventory_summary = inventory_manager.get_inventory_summary(telegram_id)
                if inventory_summary['total_wines'] > 0:
                    user_context += f"- Totale vini: {inventory_summary['total_wines']}\n"
                    user_context += f"- Quantità totale: {inventory_summary['total_quantity']} bottiglie\n"
                    user_context += f"- Scorte basse: {inventory_summary['low_stock_count']} vini\n\n"
                    
                    # Aggiungi dettagli vini
                    user_context += "DETTAGLI VINI:\n"
                    for wine in inventory_summary['wines'][:5]:  # Max 5 vini per non superare i token
                        status = "⚠️ SCORTA BASSA" if wine['low_stock'] else "✅ OK"
                        user_context += f"- {wine['name']} ({wine['producer']}) - {wine['quantity']} bottiglie {status}\n"
                else:
                    user_context += "- Inventario vuoto\n"
        
        # Sistema prompt con contesto
        system_prompt = f"""Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario vini. Sei gentile, professionale e parli in italiano.

{user_context}

CAPACITÀ:
- Analizzare l'inventario dell'utente
- Suggerire riordini per scorte basse
- Fornire consigli su gestione magazzino
- Rispondere a domande sui vini
- Generare report e statistiche
- Aiutare con l'onboarding se non completato

ISTRUZIONI:
- Usa sempre i dati dell'utente quando disponibili
- Sii specifico e pratico nei consigli
- Suggerisci comandi del bot quando appropriato
- Se l'onboarding non è completato, incoraggia a completarlo
- Se l'inventario è vuoto, suggerisci di aggiungere vini"""

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt.strip()},
            ],
            max_tokens=1500,
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



