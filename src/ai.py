import logging
from openai import OpenAI, OpenAIError
from .config import OPENAI_API_KEY, OPENAI_MODEL
from .database import db_manager

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
- Onboarding completato: {'Sì' if user.onboarding_completed else 'No'}

INVENTARIO ATTUALE:
"""
                # Ottieni inventario
                wines = db_manager.get_user_wines(telegram_id)
                if wines:
                    user_context += f"- Totale vini: {len(wines)}\n"
                    user_context += f"- Quantità totale: {sum(w.quantity for w in wines)} bottiglie\n"
                    low_stock = [w for w in wines if w.quantity <= w.min_quantity]
                    user_context += f"- Scorte basse: {len(low_stock)} vini\n\n"
                    
                    # Aggiungi dettagli vini (max 10 per limitare token)
                    user_context += "DETTAGLI VINI PRINCIPALI:\n"
                    for wine in wines[:10]:
                        status = "⚠️ SCORTA BASSA" if wine.quantity <= wine.min_quantity else "✅ OK"
                        user_context += f"- {wine.name} ({wine.producer}) - {wine.quantity} bottiglie {status}\n"
                    
                    if len(wines) > 10:
                        user_context += f"... e altri {len(wines) - 10} vini\n"
                else:
                    user_context += "- Inventario vuoto\n"
                
                # Aggiungi log recenti (ultimi 5 movimenti)
                user_context += "\nMOVIMENTI RECENTI:\n"
                logs = db_manager.get_inventory_logs(telegram_id, limit=5)
                if logs:
                    for log in logs:
                        date_str = log['movement_date'].strftime("%d/%m %H:%M")
                        tipo = "📉 Consumo" if log['movement_type'] == 'consumo' else "📈 Rifornimento"
                        user_context += f"- {date_str}: {tipo} - {log['wine_name']} ({abs(log['quantity_change'])} bot.)\n"
                else:
                    user_context += "- Nessun movimento registrato\n"
        
        # Sistema prompt con contesto
        system_prompt = f"""Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario vini. Sei gentile, professionale e parli in italiano.

{user_context}

CAPACITÀ:
- Analizzare l'inventario dell'utente in tempo reale
- Rispondere a QUALSIASI domanda o messaggio
- Suggerire riordini per scorte basse
- Fornire consigli pratici su gestione magazzino
- Analizzare movimenti e consumi
- Generare report e statistiche
- Conversazione naturale e coinvolgente

ISTRUZIONI IMPORTANTI:
- RISPONDI SEMPRE a qualsiasi messaggio, anche se non è una domanda
- Mantieni una conversazione naturale e amichevole
- Usa sempre i dati dell'inventario e dei movimenti quando disponibili
- Sii specifico e pratico nei consigli
- Se l'utente comunica consumi/rifornimenti, conferma e analizza
- Suggerisci comandi del bot quando appropriato (es: /inventario, /log)
- Se l'inventario ha scorte basse, avvisa proattivamente
- Se l'utente fa domande generiche, usa il contesto per essere specifico

ESEMPI DI RISPOSTA:
- "Ciao!" → Rispondi cordialmente e offri assistenza basata sull'inventario
- "Come va?" → Rispondi e fornisci un breve status dell'inventario
- "Ho venduto vino" → Conferma, congratulati e suggerisci di comunicare i dettagli
- Domande generali → Rispondi e collega sempre al contesto dell'inventario"""

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



