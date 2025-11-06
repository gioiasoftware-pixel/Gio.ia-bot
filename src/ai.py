import logging
import os
import re
import asyncio
from openai import OpenAI, OpenAIError
from .config import OPENAI_MODEL
from .database_async import async_db_manager
from .response_templates import (
    format_inventory_list, format_wine_quantity, format_wine_price,
    format_wine_info, format_wine_not_found, format_wine_exists,
    format_low_stock_alert, format_inventory_summary, format_movement_period_summary,
    format_search_no_results
)
from .database_async import get_movement_summary

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


def _is_general_conversation(prompt: str) -> bool:
    """
    Rileva se la domanda è una conversazione generale NON relativa all'inventario/vini.
    Se è una domanda generale, deve essere passata all'AI senza cercare vini.
    """
    p = prompt.lower().strip()
    
    # Pattern per domande generali sul bot
    general_patterns = [
        r'\b(chi\s+sei|cosa\s+fai|parlami\s+di\s+te|cosa\s+puoi\s+fare|dimmi\s+di\s+te|raccontami\s+di\s+te)',
        r'\b(aiuto|help|assistenza|supporto)',
        r'\b(ciao|salve|buongiorno|buonasera|buonanotte)',
        r'\b(grazie|prego|perfetto|ok|va bene)',
        r'\b(come\s+stai|come\s+va|tutto\s+bene)',
    ]
    
    # Se matcha pattern generali E non contiene termini relativi a vini/inventario
    wine_related_keywords = [
        'vino', 'vini', 'bottiglia', 'bottiglie', 'inventario', 'cantina', 'magazzino',
        'consumo', 'consumi', 'rifornimento', 'rifornimenti', 'venduto', 'comprato',
        'barolo', 'chianti', 'brunello', 'amarone', 'prosecco', 'champagne',
        'prezzo', 'quantità', 'annata', 'produttore', 'regione', 'toscana', 'piemonte'
    ]
    
    # Controlla se contiene pattern generali
    has_general_pattern = any(re.search(pt, p) for pt in general_patterns)
    
    # Controlla se NON contiene termini relativi a vini
    has_wine_keywords = any(kw in p for kw in wine_related_keywords)
    
    # Se ha pattern generali E non ha keyword vini, è una conversazione generale
    if has_general_pattern and not has_wine_keywords:
        return True
    
    # Se è una domanda molto corta senza keyword vini, probabilmente è generale
    if len(p.split()) <= 5 and not has_wine_keywords:
        # Controlla se contiene parole comuni di domande generali
        general_words = ['chi', 'cosa', 'come', 'perché', 'quando', 'dove', 'perché']
        if any(word in p for word in general_words):
            return True
    
    return False


def _is_inventory_list_request(prompt: str) -> bool:
    """
    Riconosce richieste tipo: che vini ho? elenco/lista inventario, mostra inventario, ecc.
    IMPORTANTE: NON matchare se la richiesta contiene filtri (region, tipo, paese, prezzo) -
    in quel caso passa all'AI che userà search_wines.
    """
    p = prompt.lower().strip()
    
    # Se contiene filtri, NON è una richiesta lista semplice → passa all'AI
    filter_keywords = [
        'della', 'del', 'dello', 'delle', 'degli', 'di', 'itali', 'frances', 'spagnol', 'tedesc',
        'toscana', 'piemonte', 'veneto', 'sicilia', 'rosso', 'bianco', 'spumante', 'rosato',
        'prezzo', 'annata', 'produttore', 'cantina', 'azienda'
    ]
    if any(kw in p for kw in filter_keywords):
        return False  # Passa all'AI con search_wines
    
    patterns = [
        r"\bche\s+vini\s+ho\b",
        r"\belenco\s+vini\b",
        r"\blista\s+vini\b",
        r"\bmostra\s+inventario\b",
        r"\bvedi\s+inventario\b",
        r"\binventario\b",
    ]
    return any(re.search(pt, p) for pt in patterns)


def _is_movement_summary_request(prompt: str) -> bool:
    """Riconosce richieste tipo: ultimi consumi/movimenti/ricavi"""
    p = prompt.lower().strip()
    patterns = [
        r"\bultimi\s+consumi\b",
        r"\bultimi\s+movimenti\b",
        r"\bconsumi\s+recenti\b",
        r"\bmovimenti\s+recenti\b",
        r"\bmi\s+dici\s+i\s+miei\s+ultimi\s+consumi\b",
        r"\bmi\s+dici\s+gli\s+ultimi\s+miei\s+consumi\b",
        r"\bultimi\s+miei\s+consumi\b",
        r"\bmostra\s+(ultimi|recenti)\s+(consumi|movimenti)\b",
        r"\briepilogo\s+(consumi|movimenti)\b",
    ]
    return any(re.search(pt, p) for pt in patterns)


async def _build_inventory_list_response(telegram_id: int, limit: int = 50) -> str:
    """Recupera l'inventario utente e lo formatta usando template pre-strutturato."""
    try:
        wines = await async_db_manager.get_user_wines(telegram_id)
        return format_inventory_list(wines, limit=limit)
    except Exception as e:
        logger.error(f"Errore creazione lista inventario: {e}")
        return "⚠️ Errore nel recupero dell'inventario. Riprova con /inventario."


def _parse_filters(prompt: str) -> dict:
    """Estrae filtri semplici dal linguaggio naturale (regioni, tipo, prezzo, annata, produttore, paese)."""
    p = prompt.lower()
    filters = {}
    
    # Paese (deve essere prima delle regioni per evitare conflitti)
    if re.search(r'\bitali[ae]?\b', p):
        filters['country'] = 'Italia'
    if re.search(r'\bfrances[ei]?\b', p):
        filters['country'] = 'Francia'
    if re.search(r'\bspagnol[oi]?\b', p):
        filters['country'] = 'Spagna'
    if re.search(r'\btedesc[hi]?\b', p):
        filters['country'] = 'Germania'
    
    # Regioni (solo se non c'è già un filtro paese o se è Italia)
    regions = [
        'toscana','toscata',  # Fix: "toscata" → "Toscana"
        'piemonte','veneto','sicilia','sardegna','lombardia','marche','umbria','lazio',
        'puglia','abruzzo','friuli','trentino','alto adige','campania','liguria','emilia','romagna'
    ]
    for r in regions:
        if r in p:
            # Normalizza variazioni
            if r == 'toscata':
                filters['region'] = 'Toscana'
            elif r == 'alto adige':
                filters['region'] = 'Alto Adige'
            else:
                filters['region'] = r.capitalize()
            break
    if re.search(r'\brossi?\b', p):
        filters['wine_type'] = 'rosso'
    if re.search(r'\bbianc[oi]\b', p):
        filters['wine_type'] = 'bianco'
    if 'spumante' in p:
        filters['wine_type'] = 'spumante'
    if 'rosato' in p:
        filters['wine_type'] = 'rosato'
    m = re.search(r'prezzo\s*(sotto|inferiore|<)\s*€?\s*(\d+[\.,]?\d*)', p)
    if m:
        filters['price_max'] = float(m.group(2).replace(',', '.'))
    m = re.search(r'prezzo\s*(sopra|maggiore|>)\s*€?\s*(\d+[\.,]?\d*)', p)
    if m:
        filters['price_min'] = float(m.group(2).replace(',', '.'))
    m = re.search(r'(?:dal|da)\s*((?:19|20)\d{2})', p)
    if m:
        filters['vintage_min'] = int(m.group(1))
    m = re.search(r'(?:fino\s*al|al)\s*((?:19|20)\d{2})', p)
    if m:
        filters['vintage_max'] = int(m.group(1))
    m = re.search(r"produttore\s+([\w\s'’]+)", p)
    if m:
        filters['producer'] = m.group(1).strip()
    return filters

async def _check_movement_with_ai(prompt: str, telegram_id: int) -> str:
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
        
        # Verifica condizioni base (stesse del check regex) - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user or not user.business_name or user.business_name == "Upload Manuale":
            return None
        
        user_wines = await async_db_manager.get_user_wines(telegram_id)
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
        
        # Usa OPENAI_MODEL dal modulo (già importato)
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,  # Importato da .config all'inizio del file
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
        
        # ✅ VALIDAZIONE OUTPUT LLM con Pydantic
        from .ai_validation import validate_movement_result
        validated = validate_movement_result(result)
        
        if validated and validated.is_movement and validated.type and validated.quantity and validated.wine_name:
            movement_type = validated.type
            quantity = validated.quantity
            wine_name = validated.wine_name.strip()
            logger.info(f"[AI-MOVEMENT] Movimento rilevato da AI (validated): {movement_type} {quantity} {wine_name}")
            return f"__MOVEMENT__:{movement_type}:{quantity}:{wine_name}"
        
        return None
        
    except json.JSONDecodeError as e:
        logger.error(f"[AI-MOVEMENT] Errore parsing JSON da AI: {e}, risposta: {result_text if 'result_text' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"[AI-MOVEMENT] Errore chiamata AI per rilevamento movimento: {e}")
        return None


async def _check_and_process_movement(prompt: str, telegram_id: int) -> str:
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
        
        # Verifica se utente esiste e ha business_name valido + inventario - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            return None  # Utente non trovato
        
        # Verifica business_name valido (non null e non "Upload Manuale")
        if not user.business_name or user.business_name == "Upload Manuale":
            return None  # Business name non valido
        
        # Verifica che l'inventario abbia almeno 1 vino
        user_wines = await async_db_manager.get_user_wines(telegram_id)
        if not user_wines or len(user_wines) == 0:
            return None  # Inventario vuoto
        
        # Se onboarding non completato ma condizioni sono soddisfatte, completa automaticamente
        if not user.onboarding_completed:
            await async_db_manager.update_user_onboarding(
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
        ai_movement_result = await _check_movement_with_ai(prompt, telegram_id)
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
        
        # Recupera business_name - ASYNC
        user = await async_db_manager.get_user_by_telegram_id(telegram_id)
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


def _format_wine_response_directly(prompt: str, telegram_id: int, found_wines: list) -> str:
    """
    Genera risposte pre-formattate colorate per domande specifiche sui vini.
    Bypassa AI per risposte immediate e ben formattate.
    """
    prompt_lower = prompt.lower().strip()
    
    # Pattern per "quanti/quante X ho"
    quantity_patterns = [
        r'quanti (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
        r'quante (.+?) (?:ho|hai|ci sono|in cantina|in magazzino)',
        r'quanti bottiglie? di (.+?) (?:ho|hai|ci sono)',
        r'quante bottiglie? di (.+?) (?:ho|hai|ci sono)',
    ]
    
    # Pattern per "quanto vendo/vendi/costa X"
    price_patterns = [
        r'a quanto (?:vendo|vendi|costano|prezzo) (.+?)',
        r'quanto (?:costa|costano|vendo|vendi) (.+?)',
        r'prezzo (.+?)',
        r'prezzo di vendita (.+?)',
    ]
    
    # Pattern per "info/dettagli/tutto su X" (più generici per catturare anche "sul X")
    info_patterns = [
        r'dimmi (?:tutto|tutte|tutta) (?:su|del|dello|della|sul) (.+?)',
        r'(?:informazioni|dettagli|info) (?:su|del|dello|della|sul) (.+?)',
        r'cosa sai (?:su|del|dello|della|sul) (.+?)',
        r'sul (.+?)(?:\?|$)',  # Pattern per "sul barolo cannubi"
        r'su (.+?)(?:\?|$)',    # Pattern per "su barolo"
        r'sul (.+)',             # Fallback senza fine frase
        r'su (.+)',              # Fallback senza fine frase
    ]
    
    # Se non ci sono vini trovati, passa all'AI
    if not found_wines:
        return None  # Passa all'AI normale
    
    wine = found_wines[0]  # Prendi il primo vino (più rilevante)
    
    # Controlla pattern "quanti X ho"
    for pattern in quantity_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_quantity(wine)
    
    # Controlla pattern "quanto vendo X"
    for pattern in price_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_price(wine)
    
    # Controlla pattern "info/dettagli su X"
    for pattern in info_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_info(wine)
    
    # Pattern per "X c'è?", "hai X?", "ce l'ho X?"
    exists_patterns = [
        r'(.+?)\s+c\'è\??',
        r'hai\s+(.+)',
        r'ce\s+l\'ho\s+(.+)',
        r'(.+?)\s+(?:è|ci sono|ce l\'hai)',
    ]
    for pattern in exists_patterns:
        if re.search(pattern, prompt_lower):
            return format_wine_exists(wine)
    
    # Fallback: se il prompt contiene "su" o "sul" e abbiamo un vino, usa sempre format_wine_info
    if re.search(r'\b(su|sul)\b', prompt_lower) and wine:
        logger.info(f"[FORMATTED] Fallback: usando format_wine_info per prompt '{prompt_lower[:50]}'")
        return format_wine_info(wine)
    
    # Se nessun pattern match, passa all'AI
    return None


async def get_ai_response(prompt: str, telegram_id: int = None, correlation_id: str = None) -> str:
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
    
    # Rileva movimenti inventario PRIMA di chiamare l'AI - ASYNC
    # Se riconosce un movimento, ritorna un marker speciale che il bot.py interpreterà
    if telegram_id:
        # Se è una conversazione generale NON relativa all'inventario, passa direttamente all'AI
        if _is_general_conversation(prompt):
            logger.info(f"[GENERAL_CONVERSATION] Rilevata conversazione generale, bypass ricerca vini")
            # Passa direttamente all'AI senza cercare vini
            # Continua oltre per chiamare l'AI normalmente
        
        # Richieste esplicite di elenco inventario: rispondi direttamente interrogando il DB
        if _is_inventory_list_request(prompt):
            return await _build_inventory_list_response(telegram_id, limit=50)

        # Richieste di riepilogo movimenti: chiedi periodo via bottoni (marker)
        if _is_movement_summary_request(prompt):
            return "[[ASK_MOVES_PERIOD]]"

        movement_marker = await _check_and_process_movement(prompt, telegram_id)
        if movement_marker and movement_marker.startswith("__MOVEMENT__:"):
            return movement_marker  # Ritorna marker che verrà processato in bot.py
    
    try:
        # Prepara il contesto utente se disponibile
        user_context = ""
        specific_wine_info = ""  # Per vini cercati specificamente
        
        if telegram_id:
            try:
                user = await async_db_manager.get_user_by_telegram_id(telegram_id)  # ASYNC
                if user:
                    # Aggiungi informazioni utente
                    user_context = f"""
INFORMAZIONI UTENTE:
- Nome attività: {user.business_name or 'Non specificato'}
- Onboarding completato: {'Sì' if user.onboarding_completed else 'No'}

INVENTARIO ATTUALE:
"""
                    # Rileva se l'utente sta chiedendo informazioni su un vino specifico
                    # Pattern ordinati dalla più specifica alla più generica
                    wine_search_patterns = [
                        # Pattern 1: "quanti/quante bottiglie di X ho/hai" (MOLTO SPECIFICO)
                        r'(?:quanti|quante)\s+bottiglie?\s+di\s+(.+?)(?:\s+ho|\s+hai|\s+ci\s+sono|\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                        # Pattern 2: "quanti/quante X ho/hai" (senza "bottiglie")
                        r'(?:quanti|quante)\s+(.+?)(?:\s+ho|\s+hai|\s+ci\s+sono|\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                        # Pattern 3: "a quanto vendo/vendi X" (prezzo)
                        r'a\s+quanto\s+(?:vendo|vendi|costano|prezzo)\s+(.+)',
                        # Pattern 4: "prezzo X"
                        r'prezzo\s+(.+)',
                        # Pattern 5: "informazioni su X"
                        r'(?:informazioni|dettagli|info)\s+(?:su|del|dello|della)\s+(.+)',
                        # Pattern 6: "X in cantina/magazzino" (generico, solo se altri non matchano)
                        r'(.+?)(?:\s+in\s+cantina|\s+in\s+magazzino|\s+quantità|$)',
                    ]
                    
                    wine_search_term = None
                    for pattern in wine_search_patterns:
                        match = re.search(pattern, prompt.lower())
                        if match:
                            wine_search_term = match.group(1).strip()
                            # Rimuovi parole comuni (incluso "bottiglie", "di", "bottiglia", ecc.)
                            wine_search_term = re.sub(r'\b(ho|hai|in|cantina|magazzino|quanti|quante|quanto|vendo|vendi|prezzo|informazioni|dettagli|info|su|del|dello|della|bottiglie|bottiglia|di|mi|dici|dirmi)\b', '', wine_search_term, flags=re.IGNORECASE).strip()
                            # Rimuovi spazi multipli
                            wine_search_term = re.sub(r'\s+', ' ', wine_search_term).strip()
                            if wine_search_term and len(wine_search_term) > 2:  # Almeno 3 caratteri
                                logger.info(f"Rilevata ricerca vino specifico: '{wine_search_term}'")
                                break
                    
                    # Se è stata rilevata una ricerca, cerca nel database - ASYNC
                    # Ma solo se NON è una conversazione generale
                    if wine_search_term and not _is_general_conversation(prompt):
                        found_wines = await async_db_manager.search_wines(telegram_id, wine_search_term, limit=10)
                        if found_wines:
                            # Se ci sono più corrispondenze, restituisci marker per selezione con pulsanti
                            if len(found_wines) > 1:
                                logger.info(f"[WINE_SELECTION] Trovati {len(found_wines)} vini per '{wine_search_term}', richiesta selezione")
                                # Marker che verrà processato in bot.py per mostrare pulsanti
                                return f"[[WINE_SELECTION:{wine_search_term}]]"
                            
                            # Prova a generare risposta pre-formattata (bypass AI per domande specifiche)
                            formatted_response = _format_wine_response_directly(prompt, telegram_id, found_wines)
                            if formatted_response:
                                logger.info(f"[FORMATTED] Risposta pre-formattata generata per domanda specifica")
                                return formatted_response
                            
                            # Se non è una domanda specifica, passa info all'AI nel contesto
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
                            # Anche se non trovato, passa all'AI per gestire il messaggio
                            # (AI dirà "non ho questa informazione" in modo più naturale)
                    else:
                        # Retry 1: ricerca ampia usando l'intero prompt come termine di ricerca
                        try:
                            broad_term = re.sub(r"[^\w\s'’]", " ", prompt.lower()).strip()
                            if broad_term and len(broad_term) > 2:
                                broad_found = await async_db_manager.search_wines(telegram_id, broad_term, limit=3)
                                if broad_found and len(broad_found) == 1:
                                    logger.info("[FORMATTED] Retry broad search matched exactly 1 wine → template info")
                                    return format_wine_info(broad_found[0])
                        except Exception as e:
                            logger.warning(f"Broad search fallback failed: {e}")
                    
                    # Ottieni statistiche inventario (non tutti i vini)
                    wines = await async_db_manager.get_user_wines(telegram_id)  # ASYNC
                    if wines:
                        user_context += f"- Totale vini: {len(wines)}\n"
                        user_context += f"- Quantità totale: {sum(w.quantity for w in wines)} bottiglie\n"
                        low_stock = [w for w in wines if w.quantity <= w.min_quantity]
                        user_context += f"- Scorte basse: {len(low_stock)} vini\n"
                        user_context += "\nNOTA: I dettagli dei vini specifici vengono cercati direttamente nel database quando richiesto.\n"
                    else:
                        user_context += "- Inventario vuoto\n"
                    
                    # Nota: I movimenti inventario sono ora gestiti dalla tabella "Consumi e rifornimenti"
                    # I log interazione contengono solo messaggi utente, non movimenti
                    # user_context += "\nMOVIMENTI RECENTI:\n"  # Disabilitato - usa tabella Consumi
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
- CONSULTA SEMPRE il database prima di rispondere a qualsiasi domanda informativa
- RISPONDI SEMPRE a qualsiasi messaggio, anche se non è una domanda
- Mantieni una conversazione naturale e amichevole
- Usa sempre i dati dell'inventario e dei movimenti quando disponibili
- Sii specifico e pratico nei consigli
- Se l'utente comunica consumi/rifornimenti, conferma e analizza
- Suggerisci comandi del bot quando appropriato (es: /inventario, /log)
- Se l'inventario ha scorte basse, avvisa proattivamente
- Se l'utente fa domande generiche, usa il contesto per essere specifico

REGOLA CRITICA PER RICERCHE FILTRATE:
- Se l'utente chiede vini con QUALSIASI filtro geografico/tipo/prezzo/annata (es. "della Toscana", "italiani", "rossi", "sotto €50"), DEVI chiamare search_wines con i filtri estratti
- NON usare get_inventory_list se ci sono filtri nella richiesta
- Estrai filtri dal testo: "della Toscana" → {{"region": "Toscana"}}, "italiani" → {{"country": "Italia"}}, "rossi" → {{"wine_type": "rosso"}}
- Combina filtri quando presenti: "rossi italiani" → {{"country": "Italia", "wine_type": "rosso"}}

FORMATO RISPOSTE PRE-STRUTTURATE:
Per domande informative, usa questi formati con dati reali dal database:

1. ELENCO INVENTARIO ("che vini ho?", "lista inventario"):
📋 **Il tuo inventario**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Nome Vino (Produttore) Annata — quantità bott. - €prezzo
2. ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2. QUANTITÀ VINO ("quanti X ho?"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 **In cantina hai:** X bottiglie
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3. PREZZO VINO ("a quanto vendo X?"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 **Prezzo vendita:** €XX.XX
💵 **Prezzo acquisto:** €XX.XX
📊 **Margine:** €XX.XX (XX%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

4. INFO COMPLETE VINO ("dimmi tutto su X"):
🍷 **Nome Vino (Produttore)**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏭 **Produttore:** ...
📍 **Regione:** ...
📅 **Annata:** ...
🍇 **Vitigno:** ...
📦 **Quantità:** X bottiglie
🔴/⚪ **Tipo:** ...
⭐ **Classificazione:** ...
💰 **Prezzo vendita:** €XX.XX
💵 **Prezzo acquisto:** €XX.XX
🍾 **Gradazione:** XX% vol
📝 **Descrizione:** ...
💬 **Note:** ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

5. VINO NON TROVATO:
❌ **Vino non trovato**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Non ho trovato 'nome' nel tuo inventario.
💡 **Cosa puoi fare:**
• Controlla l'ortografia del nome
• Usa /inventario per vedere tutti i vini
• Usa /aggiungi per aggiungere un nuovo vino
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

6. VINO PRESENTE ("X c'è?"):
✅ **Sì, ce l'hai!**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🍷 **Nome Vino (Produttore)** con X bottiglie
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REGOLA D'ORO: Prima di rispondere a qualsiasi domanda informativa, consulta SEMPRE il database usando i dati forniti nel contesto o cerca il vino specifico se necessario."""
        
        # Suggerimento forte per l'AI: se la richiesta corrisponde a uno dei casi (quantità, prezzo, info vino, elenco),
        # usa il formato pre-strutturato corrispondente. Solo se non applicabile, rispondi in modo colloquiale
        # ma sempre basandoti sui dati del database quando disponibili.
        
        logger.info(f"System prompt length: {len(system_prompt)}")
        logger.info(f"User prompt: {prompt[:100]}...")

        # Recupera storico conversazione (ultimi 10 messaggi) e costruisci chat
        history_messages = []
        if telegram_id:
            try:
                history = await async_db_manager.get_recent_chat_messages(telegram_id, limit=10)
                for h in history:
                    if h.get('role') in ('user', 'assistant') and h.get('content'):
                        history_messages.append({"role": h['role'], "content": h['content']})
            except Exception as e:
                logger.warning(f"Impossibile recuperare chat history per {telegram_id}: {e}")

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
        # Definizione tools (function calling) per accesso deterministico ai dati
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_list",
                    "description": "Restituisce l'elenco dei vini dell'utente corrente con quantità e prezzi.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Numero massimo di vini da elencare", "default": 50}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_info",
                    "description": "Restituisce le informazioni dettagliate di un vino presente nell'inventario utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino da cercare"}
                        },
                        "required": ["wine_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_price",
                    "description": "Restituisce i prezzi (vendita/acquisto) per un vino dell'utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino"}
                        },
                        "required": ["wine_query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_quantity",
                    "description": "Restituisce la quantità in magazzino per un vino dell'utente.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_query": {"type": "string", "description": "Nome o parte del nome del vino"}
                        },
                        "required": ["wine_query"]
                    }
                }
            }
        ]
        # Ricerca filtrata e riepilogo inventario
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "search_wines",
                    "description": """Cerca vini applicando filtri multipli. USA QUESTA FUNZIONE quando l'utente chiede vini con criteri specifici:
- Geografici: 'della Toscana', 'italiani', 'del Piemonte', 'francesi', ecc.
- Tipo: 'rossi', 'bianchi', 'spumanti', 'rosati'
- Prezzo: 'prezzo sotto X', 'prezzo sopra Y'
- Annata: 'dal 2015', 'fino al 2020'
- Produttore: 'produttore X', 'cantina Y'
- Combinati: 'rossi toscani', 'italiani sotto €50'

IMPORTANTE: Se la richiesta contiene QUALSIASI filtro, usa questa funzione invece di get_inventory_list.
Formato filters: {"region": "Toscana", "country": "Italia", "wine_type": "rosso", "price_max": 50, "vintage_min": 2015, "producer": "nome", "name_contains": "testo"}""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filters": {
                                "type": "object",
                                "properties": {
                                    "region": {"type": "string", "description": "Regione italiana (es. 'Toscana', 'Piemonte')"},
                                    "country": {"type": "string", "description": "Paese (es. 'Italia', 'Francia', 'Spagna')"},
                                    "wine_type": {"type": "string", "enum": ["rosso", "bianco", "rosato", "spumante"]},
                                    "classification": {"type": "string"},
                                    "producer": {"type": "string", "description": "Nome produttore/cantina"},
                                    "name_contains": {"type": "string", "description": "Testo contenuto nel nome vino"},
                                    "price_min": {"type": "number", "description": "Prezzo minimo vendita"},
                                    "price_max": {"type": "number", "description": "Prezzo massimo vendita"},
                                    "vintage_min": {"type": "integer", "description": "Annata minima (es. 2015)"},
                                    "vintage_max": {"type": "integer", "description": "Annata massima (es. 2020)"},
                                    "quantity_min": {"type": "integer"},
                                    "quantity_max": {"type": "integer"}
                                }
                            },
                            "limit": {"type": "integer", "default": 50}
                        },
                        "required": ["filters"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_stats",
                    "description": "Ritorna il riepilogo inventario (totale vini, totale bottiglie, prezzi media/min/max, low stock).",
                    "parameters": {"type": "object", "properties": {}},
                }
            }
        ])
        tools.append({
            "type": "function",
            "function": {
                "name": "get_movement_summary",
                "description": "Riepiloga consumi/rifornimenti per un periodo (day/week/month). Se periodo mancante, chiedilo all'utente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "period": {"type": "string", "enum": ["day", "week", "month"], "description": "Periodo del riepilogo"}
                    },
                    "required": []
                }
            }
        })
        # ✅ NUOVI TOOL: Movimenti e funzioni aggiuntive
        tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "register_consumption",
                    "description": "Registra un consumo (vendita/consumo) di bottiglie. Diminuisce la quantità disponibile del vino specificato.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_name": {"type": "string", "description": "Nome del vino da consumare"},
                            "quantity": {"type": "integer", "description": "Numero di bottiglie consumate (deve essere positivo)"}
                        },
                        "required": ["wine_name", "quantity"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "register_replenishment",
                    "description": "Registra un rifornimento (acquisto/aggiunta) di bottiglie. Aumenta la quantità disponibile del vino specificato.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_name": {"type": "string", "description": "Nome del vino da rifornire"},
                            "quantity": {"type": "integer", "description": "Numero di bottiglie aggiunte (deve essere positivo)"}
                        },
                        "required": ["wine_name", "quantity"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_low_stock_wines",
                    "description": "Ottiene lista vini con scorte basse (quantità inferiore alla soglia). Utile per identificare vini da rifornire.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "threshold": {"type": "integer", "description": "Soglia minima quantità (vini con quantità < threshold vengono segnalati)", "default": 5}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_wine_details",
                    "description": "Ottiene dettagli completi di un vino specifico: nome, produttore, annata, quantità, prezzo, regione, tipo, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "wine_id": {"type": "integer", "description": "ID del vino di cui ottenere i dettagli"}
                        },
                        "required": ["wine_id"]
                    }
                }
            }
        ])

        # Chiamata API con gestione errori robusta
        try:
            logger.info(f"Chiamata API OpenAI - Model: {OPENAI_MODEL}")
            messages = [{"role": "system", "content": system_prompt}]
            # Aggiungi storico conversazione (già normalizzato)
            messages.extend(history_messages)
            # Aggiungi ultimo messaggio utente
            messages.append({"role": "user", "content": prompt.strip()})

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
                tools=tools,
                tool_choice="auto"
            )
            logger.info("Chiamata API OpenAI completata con successo")
        except Exception as e:
            logger.error(f"Errore chiamata API OpenAI: {e}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            # Fallback: se la richiesta contiene filtri riconoscibili, esegui ricerca locale senza AI
            try:
                if telegram_id:
                    derived = _parse_filters(prompt)
                    if derived:
                        wines = await async_db_manager.search_wines_filtered(telegram_id, derived, limit=50)
                        if wines:
                            return format_inventory_list(wines, limit=50)
                        return format_search_no_results(derived)
            except Exception as fe:
                logger.error(f"Fallback ricerca filtrata fallito: {fe}")
            return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
        
        # Se l'AI ha scelto di chiamare un tool, gestiscilo qui (function calling)
        choice = response.choices[0]
        message = choice.message

        # Gestione tool calls
        try:
            tool_calls = getattr(message, "tool_calls", None)
        except Exception:
            tool_calls = None

        if tool_calls and telegram_id:
            # Esegui la prima tool call rilevante (una risposta deterministica e rapida)
            call = tool_calls[0]
            fn = call.function
            name = getattr(fn, "name", "")
            import json as _json
            args = {}
            try:
                args = _json.loads(getattr(fn, "arguments", "{}") or "{}")
            except Exception:
                args = {}

            logger.info(f"[TOOLS] AI ha richiesto tool: {name} args={args}")

            # ✅ USA FUNCTION EXECUTOR (centralizzato)
            try:
                from .function_executor import FunctionExecutor
                
                # Crea executor (context non disponibile in ai.py, passa None)
                executor = FunctionExecutor(telegram_id, None)
                result = await executor.execute_function(name, args)
                
                # ✅ Se template disponibile, usa direttamente (NO re-chiamata AI)
                if result.get("use_template") and result.get("formatted_message"):
                    logger.info(f"[TOOLS] Risposta formattata con template (NO re-chiamata AI)")
                    return result["formatted_message"]
                
                # Se success ma no template, ritorna messaggio di successo
                if result.get("success"):
                    return result.get("formatted_message", result.get("message", "✅ Operazione completata"))
                
                # Se errore, ritorna messaggio errore
                error_msg = result.get("error", "Errore sconosciuto")
                return f"❌ {error_msg}"
                
            except ImportError:
                # FunctionExecutor non disponibile, usa fallback inline (compatibilità)
                logger.warning(f"[TOOLS] FunctionExecutor non disponibile, usando fallback inline")
                pass
            except Exception as e:
                logger.error(f"[TOOLS] Errore FunctionExecutor: {e}", exc_info=True)
                # Fallback a logica inline
                pass
            
            # ✅ FALLBACK: Implementazioni tool inline (per compatibilità)
            if name == "get_inventory_list":
                limit = int(args.get("limit", 50))
                return await _build_inventory_list_response(telegram_id, limit=limit)

            if name == "get_wine_info":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                wines = await async_db_manager.search_wines(telegram_id, query, limit=1)
                if wines:
                    return format_wine_info(wines[0])
                return format_wine_not_found(query)

            if name == "get_wine_price":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                wines = await async_db_manager.search_wines(telegram_id, query, limit=1)
                if wines:
                    return format_wine_price(wines[0])
                return format_wine_not_found(query)

            if name == "get_wine_quantity":
                query = (args.get("wine_query") or "").strip()
                if not query:
                    return "❌ Richiesta incompleta: specifica il vino."
                wines = await async_db_manager.search_wines(telegram_id, query, limit=1)
                if wines:
                    return format_wine_quantity(wines[0])
                return format_wine_not_found(query)

            if name == "search_wines":
                filters = args.get("filters") or {}
                limit = int(args.get("limit", 50))
                
                # Arricchisci filtri dal prompt (parser fallback se AI non ha estratto tutto)
                derived = _parse_filters(prompt)
                # Merge: derived ha priorità (più accurato), poi filtri AI, poi derived se mancanti
                merged_filters = {**filters, **{k: v for k, v in derived.items() if k not in filters or not filters.get(k)}}
                
                logger.info(f"[SEARCH] Filtri applicati: {merged_filters}")
                wines = await async_db_manager.search_wines_filtered(telegram_id, merged_filters, limit=limit)
                
                if wines:
                    return format_inventory_list(wines, limit=limit)
                return format_search_no_results(merged_filters)

            if name == "get_inventory_stats":
                stats = await async_db_manager.get_inventory_stats(telegram_id)
                return format_inventory_summary(
                    telegram_id,
                    stats.get('total_wines', 0),
                    stats.get('total_bottles', 0),
                    stats.get('low_stock', 0)
                )

            if name == "get_movement_summary":
                period = (args.get("period") or "").strip()
                if not period:
                    return "[[ASK_MOVES_PERIOD]]"
                try:
                    totals = await get_movement_summary(telegram_id, period)
                    return format_movement_period_summary(period, totals)
                except Exception as e:
                    logger.error(f"Errore get_movement_summary tool: {e}")
                    return "⚠️ Errore nel calcolo dei movimenti. Riprova."
            
            # Tool non riconosciuto
            logger.warning(f"[TOOLS] Tool '{name}' non riconosciuto nel fallback")
            return f"⚠️ Funzione '{name}' non ancora implementata."

        # Nessuna tool call: usa il contenuto generato
        content = getattr(message, "content", "") or ""
        if not content.strip():
            logger.error("Risposta vuota da OpenAI")
            return "⚠️ Errore nella generazione della risposta. Riprova."
        return content.strip()
        
    except OpenAIError as e:
        logger.error(f"Errore OpenAI: {e}")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."
    except Exception as e:
        logger.error(f"Errore imprevisto in get_ai_response: {e}")
        logger.error(f"Tipo errore: {type(e).__name__}")
        logger.error(f"Prompt ricevuto: {prompt[:100]}...")
        return "⚠️ Errore temporaneo dell'AI. Riprova tra qualche minuto."



