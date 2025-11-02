import logging
import os
import re
import asyncio
from openai import OpenAI, OpenAIError
from .config import OPENAI_MODEL
from .database import db_manager

# Carica direttamente la variabile ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Disabilita eventuali proxy automatici che potrebbero causare conflitti
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

logger = logging.getLogger(__name__)


def _check_movement_with_ai(prompt: str, telegram_id: int) -> str:
    """
    Usa OpenAI per rilevare se il messaggio è un movimento inventario quando regex non match.
    Gestisce variazioni linguistiche naturali come "mi sono arrivati", "arrivati", ecc.
    """
    try:
        import json
        import openai
        
        # Usa le variabili già definite nel modulo
        if not OPENAI_API_KEY:
            return None
        
        # Verifica condizioni base (stesse del check regex)
        user = db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name or user.business_name == "Upload Manuale":
            return None
        
        user_wines = db_manager.get_user_wines(telegram_id)
        if not user_wines or len(user_wines) == 0:
            return None
        
        # Prompt specifico per rilevare movimenti
        movement_detection_prompt = f"""Analizza questo messaggio e determina se indica un movimento inventario (consumo o rifornimento di vini).

MESSAGGIO: "{prompt}"

Un movimento può essere espresso in molti modi:
- Rifornimento: "mi sono arrivati X vini", "arrivati X", "sono arrivati X", "ho ricevuto X", "comprato X", ecc.
- Consumo: "ho venduto X", "ho consumato X", "ho bevuto X", "venduto X", ecc.

Rispondi SOLO con un JSON valido in questo formato (senza testo aggiuntivo):
{{
    "is_movement": true o false,
    "type": "consumo" o "rifornimento" o null,
    "quantity": numero intero o null,
    "wine_name": "nome del vino" o null
}}

Esempi:
- "mi sono arrivati 6 gavi" → {{"is_movement": true, "type": "rifornimento", "quantity": 6, "wine_name": "gavi"}}
- "ho consumato 5 sassicaia" → {{"is_movement": true, "type": "consumo", "quantity": 5, "wine_name": "sassicaia"}}
- "quanti vini ho?" → {{"is_movement": false, "type": null, "quantity": null, "wine_name": null}}
"""
        
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Sei un analizzatore di messaggi. Rispondi SOLO con JSON valido, senza testo aggiuntivo."},
                {"role": "user", "content": movement_detection_prompt}
            ],
            max_tokens=150,
            temperature=0.1  # Bassa temperatura per risposte più deterministiche
        )
        
        if not response.choices or not response.choices[0].message.content:
            return None
        
        result_text = response.choices[0].message.content.strip()
        logger.info(f"[AI-MOVEMENT] Risposta AI rilevamento: {result_text}")
        
        # Estrai JSON dalla risposta (potrebbe essere in un code block)
        json_text = result_text
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(json_text)
        
        if result.get("is_movement") and result.get("type") and result.get("quantity") and result.get("wine_name"):
            movement_type = result["type"]
            quantity = int(result["quantity"])
            wine_name = result["wine_name"].strip()
            logger.info(f"[AI-MOVEMENT] Movimento rilevato da AI: {movement_type} {quantity} {wine_name}")
            return f"__MOVEMENT__:{movement_type}:{quantity}:{wine_name}"
        
        return None
        
    except json.JSONDecodeError as e:
        logger.error(f"[AI-MOVEMENT] Errore parsing JSON da AI: {e}, risposta: {result_text if 'result_text' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore chiamata AI per rilevamento movimento: {e}")
        return None


def _check_and_process_movement(prompt: str, telegram_id: int) -> str:
    """
    Rileva se il prompt contiene un movimento inventario (consumo/rifornimento).
    Se sì, lo processa direttamente e ritorna il messaggio di conferma.
    Se no, ritorna None e il flow continua normalmente con l'AI.
    """
    try:
        prompt_lower = prompt.lower().strip()
        
        # Pattern per consumo
        consumo_patterns = [
            r'ho venduto (\d+) bottiglie? di (.+)',
            r'ho consumato (\d+) bottiglie? di (.+)',
            r'ho bevuto (\d+) bottiglie? di (.+)',
            r'ho venduto (\d+) (.+)',
            r'ho consumato (\d+) (.+)',
            r'ho bevuto (\d+) (.+)',
            r'venduto (\d+) (.+)',
            r'consumato (\d+) (.+)',
            r'bevuto (\d+) (.+)',
        ]
        
        # Pattern per rifornimento
        rifornimento_patterns = [
            r'ho ricevuto (\d+) bottiglie? di (.+)',
            r'ho comprato (\d+) bottiglie? di (.+)',
            r'ho aggiunto (\d+) bottiglie? di (.+)',
            r'ho ricevuto (\d+) (.+)',
            r'ho comprato (\d+) (.+)',
            r'ho aggiunto (\d+) (.+)',
            r'ricevuto (\d+) (.+)',
            r'comprato (\d+) (.+)',
            r'aggiunto (\d+) (.+)',
        ]
        
        # Verifica se utente esiste e ha business_name valido + inventario
        user = db_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            return None  # Utente non trovato
        
        # Verifica business_name valido (non null e non "Upload Manuale")
        if not user.business_name or user.business_name == "Upload Manuale":
            return None  # Business name non valido
        
        # Verifica che l'inventario abbia almeno 1 vino
        user_wines = db_manager.get_user_wines(telegram_id)
        if not user_wines or len(user_wines) == 0:
            return None  # Inventario vuoto
        
        # Se onboarding non completato ma condizioni sono soddisfatte, completa automaticamente
        if not user.onboarding_completed:
            db_manager.update_user_onboarding(
                telegram_id=telegram_id,
                onboarding_completed=True
            )
            logger.info(f"[AI-MOVEMENT] Onboarding completato automaticamente per {telegram_id} (business_name={user.business_name}, {len(user_wines)} vini)")
        
        # Cerca pattern consumo
        for pattern in consumo_patterns:
            match = re.search(pattern, prompt_lower)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                logger.info(f"[AI-MOVEMENT] Rilevato consumo: {quantity} {wine_name}")
                # Ritorna marker che verrà processato in bot.py
                return f"__MOVEMENT__:consumo:{quantity}:{wine_name}"
        
        # Cerca pattern rifornimento
        for pattern in rifornimento_patterns:
            match = re.search(pattern, prompt_lower)
            if match:
                quantity = int(match.group(1))
                wine_name = match.group(2).strip()
                logger.info(f"[AI-MOVEMENT] Rilevato rifornimento (regex): {quantity} {wine_name}")
                # Ritorna marker che verrà processato in bot.py
                return f"__MOVEMENT__:rifornimento:{quantity}:{wine_name}"
        
        # Se regex non ha matchato, usa AI per rilevare movimenti con variazioni linguistiche
        logger.info(f"[AI-MOVEMENT] Regex non matchato, provo con AI per: {prompt_lower[:50]}")
        ai_movement_result = _check_movement_with_ai(prompt, telegram_id)
        if ai_movement_result:
            logger.info(f"[AI-MOVEMENT] Rilevato movimento tramite AI: {ai_movement_result}")
            return ai_movement_result
        
        return None  # Nessun movimento rilevato
        
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore rilevamento movimento: {e}")
        return None  # In caso di errore, passa all'AI normale


async def _process_movement_async(telegram_id: int, wine_name: str, movement_type: str, quantity: int) -> str:
    """
    Processa movimento in modo asincrono.
    Usato quando l'AI rileva un movimento direttamente dal prompt.
    """
    try:
        from .processor_client import processor_client
        
        # Recupera business_name
        user = db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name:
            return "❌ **Errore**: Nome locale non trovato.\nCompleta prima l'onboarding con `/start`."
        
        business_name = user.business_name
        
        # Processa movimento
        result = await processor_client.process_movement(
            telegram_id=telegram_id,
            business_name=business_name,
            wine_name=wine_name,
            movement_type=movement_type,
            quantity=quantity
        )
        
        if result.get('status') == 'success':
            if movement_type == 'consumo':
                return (
                    f"✅ **Consumo registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name')}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📉 **Consumate:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
            else:
                return (
                    f"✅ **Rifornimento registrato**\n\n"
                    f"🍷 **Vino:** {result.get('wine_name')}\n"
                    f"📦 **Quantità:** {result.get('quantity_before')} → {result.get('quantity_after')} bottiglie\n"
                    f"📈 **Aggiunte:** {quantity} bottiglie\n\n"
                    f"💾 **Movimento salvato** nel sistema"
                )
        else:
            error_msg = result.get('error', 'Errore sconosciuto')
            if 'non trovato' in error_msg.lower():
                return (
                    f"❌ **Vino non trovato**\n\n"
                    f"Non ho trovato '{wine_name}' nel tuo inventario.\n"
                    f"💡 Controlla il nome o usa `/inventario` per vedere i vini disponibili."
                )
            elif 'insufficiente' in error_msg.lower():
                return (
                    f"⚠️ **Quantità insufficiente**\n\n"
                    f"{error_msg}\n\n"
                    f"💡 Verifica la quantità o aggiorna l'inventario."
                )
            else:
                return f"❌ **Errore durante l'aggiornamento**\n\n{error_msg[:200]}\n\nRiprova più tardi."
                
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore processamento movimento: {e}")
        return f"❌ **Errore durante il processamento**\n\nErrore: {str(e)[:200]}\n\nRiprova più tardi."


def get_ai_response(prompt: str, telegram_id: int = None) -> str:
    """Genera risposta AI con accesso ai dati utente."""
    logger.info(f"=== DEBUG OPENAI ===")
    logger.info(f"OPENAI_API_KEY presente: {bool(OPENAI_API_KEY)}")
    logger.info(f"OPENAI_API_KEY valore: {OPENAI_API_KEY[:10] if OPENAI_API_KEY else 'None'}...")
    logger.info(f"OPENAI_MODEL: {OPENAI_MODEL}")
    
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key non configurata")
        return "⚠️ L'AI non è configurata. Contatta l'amministratore."
    
    if not prompt or not prompt.strip():
        logger.warning("Prompt vuoto ricevuto")
        return "⚠️ Messaggio vuoto ricevuto. Prova a scrivere qualcosa!"
    
    # Rileva movimenti inventario PRIMA di chiamare l'AI
    # Se riconosce un movimento, ritorna un marker speciale che il bot.py interpreterà
    if telegram_id:
        movement_marker = _check_and_process_movement(prompt, telegram_id)
        if movement_marker and movement_marker.startswith("__MOVEMENT__:"):
            return movement_marker  # Ritorna marker che verrà processato in bot.py
    
    try:
        # Prepara il contesto utente se disponibile
        user_context = ""
        specific_wine_info = ""  # Per vini cercati specificamente
        
        if telegram_id:
            try:
                user = db_manager.get_user_by_telegram_id(telegram_id)
                if user:
                    # Aggiungi informazioni utente
                    user_context = f"""
INFORMAZIONI UTENTE:
- Nome attività: {user.business_name or 'Non specificato'}
- Onboarding completato: {'Sì' if user.onboarding_completed else 'No'}

INVENTARIO ATTUALE:
"""
                    # Rileva se l'utente sta chiedendo informazioni su un vino specifico
                    wine_search_patterns = [
                        r'quanti (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
                        r'quanto (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
                        r'a quanto (?:vendo|vendi|costano|costano|prezzo) (.+?)',
                        r'prezzo (.+?)',
                        r'(.+?) (?:in cantina|in magazzino|ho|hai|quantità)',
                        r'(?:informazioni|dettagli|info) (?:su|del|dello|della) (.+?)',
                    ]
                    
                    wine_search_term = None
                    for pattern in wine_search_patterns:
                        match = re.search(pattern, prompt.lower())
                        if match:
                            wine_search_term = match.group(1).strip()
                            # Rimuovi parole comuni
                            wine_search_term = re.sub(r'\b(ho|hai|in|cantina|magazzino|quanti|quanto|vendo|prezzo|informazioni|dettagli|info|su|del|dello|della)\b', '', wine_search_term).strip()
                            if wine_search_term:
                                logger.info(f"Rilevata ricerca vino specifico: '{wine_search_term}'")
                                break
                    
                    # Se è stata rilevata una ricerca, cerca nel database
                    if wine_search_term:
                        found_wines = db_manager.search_wines(telegram_id, wine_search_term, limit=5)
                        if found_wines:
                            specific_wine_info = "\n\nVINI TROVATI NEL DATABASE PER LA RICERCA:\n"
                            for wine in found_wines:
                                info_parts = [f"- {wine.name}"]
                                if wine.vintage:
                                    info_parts.append(f"Annata: {wine.vintage}")
                                if wine.producer:
                                    info_parts.append(f"Produttore: {wine.producer}")
                                if wine.quantity is not None:
                                    info_parts.append(f"Quantità: {wine.quantity} bottiglie")
                                if wine.selling_price:
                                    info_parts.append(f"Prezzo vendita: €{wine.selling_price:.2f}")
                                if wine.cost_price:
                                    info_parts.append(f"Prezzo acquisto: €{wine.cost_price:.2f}")
                                if wine.region:
                                    info_parts.append(f"Regione: {wine.region}")
                                if wine.country:
                                    info_parts.append(f"Paese: {wine.country}")
                                specific_wine_info += " | ".join(info_parts) + "\n"
                        else:
                            specific_wine_info = f"\n\nNESSUN VINO TROVATO nel database per '{wine_search_term}'\n"
                    
                    # Ottieni statistiche inventario (non tutti i vini)
                    wines = db_manager.get_user_wines(telegram_id)
                    if wines:
                        user_context += f"- Totale vini: {len(wines)}\n"
                        user_context += f"- Quantità totale: {sum(w.quantity for w in wines)} bottiglie\n"
                        low_stock = [w for w in wines if w.quantity <= w.min_quantity]
                        user_context += f"- Scorte basse: {len(low_stock)} vini\n"
                        user_context += "\nNOTA: I dettagli dei vini specifici vengono cercati direttamente nel database quando richiesto.\n"
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
            except Exception as e:
                logger.error(f"Errore accesso database per utente {telegram_id}: {e}")
                user_context = "- Database temporaneamente non disponibile\n"
        
        # Sistema prompt con contesto
        system_prompt = f"""Sei Gio.ia-bot, un assistente AI specializzato nella gestione inventario vini. Sei gentile, professionale e parli in italiano.

{user_context}{specific_wine_info}

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
        
        logger.info(f"System prompt length: {len(system_prompt)}")
        logger.info(f"User prompt: {prompt[:100]}...")

        # Configura client OpenAI versione 2.x
        try:
            import openai
            logger.info(f"OpenAI version: {openai.__version__}")
            
            # Crea client OpenAI con configurazione semplice
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            logger.info("Client OpenAI creato con successo")
        except Exception as e:
            logger.error(f"Errore creazione client OpenAI: {e}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            logger.error(f"Errore completo: {str(e)}")
            return "Ciao! 👋 Sono Gio.ia-bot, il tuo assistente per la gestione inventario vini. Al momento l'AI è temporaneamente non disponibile, ma puoi usare i comandi /help per vedere le funzionalità disponibili!"
        # Chiamata API con gestione errori robusta
        try:
            logger.info(f"Chiamata API OpenAI - Model: {OPENAI_MODEL}")
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt.strip()},
                ],
                max_tokens=1500,
                temperature=0.7
            )
            logger.info("Chiamata API OpenAI completata con successo")
        except Exception as e:
            logger.error(f"Errore chiamata API OpenAI: {e}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
        
        if not response.choices or not response.choices[0].message.content:
            logger.error("Risposta vuota da OpenAI")
            return "⚠️ Errore nella generazione della risposta. Riprova."
            
        return response.choices[0].message.content.strip()
        
    except OpenAIError as e:
        logger.error(f"Errore OpenAI: {e}")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
    except Exception as e:
        logger.error(f"Errore imprevisto in get_ai_response: {e}")
        logger.error(f"Tipo errore: {type(e).__name__}")
        logger.error(f"Prompt ricevuto: {prompt[:100]}...")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."



