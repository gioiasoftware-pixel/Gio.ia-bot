"""
Database async per Gio.ia-bot - Gestione utenti e inventario vini (ASYNC)
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text as sql_text, Column, Integer, BigInteger, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

# Base per i modelli SQLAlchemy
Base = declarative_base()

# MODELLI (stessi di database.py ma per async)
class User(Base):
    """Modello per gli utenti del bot"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Dati onboarding
    business_name = Column(String(200))
    business_type = Column(String(100))
    location = Column(String(200))
    phone = Column(String(50))
    email = Column(String(200))
    onboarding_completed = Column(Boolean, default=False)


class Wine(Base):
    """Modello per l'inventario vini (per fallback)"""
    __tablename__ = 'wines'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(200), nullable=False)
    producer = Column(String(200))
    vintage = Column(Integer)
    grape_variety = Column(String(200))
    region = Column(String(200))
    country = Column(String(100))
    wine_type = Column(String(50))
    classification = Column(String(100))
    quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=0)
    cost_price = Column(Float)
    selling_price = Column(Float)
    alcohol_content = Column(Float)
    description = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# URL DATABASE
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://user:password@localhost/gioia_bot"
    logger.warning("DATABASE_URL non trovata, usando fallback locale")
else:
    logger.info(f"DATABASE_URL trovata: {DATABASE_URL[:20]}...")

# Converte URL Railway in formato SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Fix per URL malformate di Railway
if "port" in DATABASE_URL and not DATABASE_URL.count(":") >= 3:
    logger.warning("DATABASE_URL malformata, usando fallback")
    DATABASE_URL = "postgresql://user:password@localhost/gioia_bot"

# Converti a asyncpg
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# ENGINE ASYNC
engine = create_async_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=0,  # IMPORTANTE: evita superare max_connections
    pool_pre_ping=True,  # Auto-reconnect
    echo=False,
)

# SESSION FACTORY ASYNC
AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_async_session() -> AsyncSession:
    """Ottieni sessione async"""
    return AsyncSessionLocal()


class AsyncDatabaseManager:
    """Gestore database async per bot"""
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Trova utente per Telegram ID"""
        async with await get_async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def get_all_users(self) -> List[User]:
        """Ottieni tutti gli utenti"""
        async with await get_async_session() as session:
            result = await session.execute(select(User))
            return list(result.scalars().all())
    
    async def create_user(self, telegram_id: int, username: str = None, 
                         first_name: str = None, last_name: str = None) -> User:
        """Crea nuovo utente"""
        async with await get_async_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Nuovo utente creato: {user.telegram_id}")
            return user
    
    async def update_user_onboarding(self, telegram_id: int, **kwargs) -> bool:
        """Aggiorna onboarding utente"""
        async with await get_async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return False
            
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            user.updated_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Onboarding aggiornato per utente {telegram_id}")
            return True
    
    async def get_user_wines(self, telegram_id: int) -> List[Wine]:
        """Ottieni vini utente da tabelle dinamiche"""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                logger.warning(f"User {telegram_id} non trovato o business_name mancante")
                return []
            
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            
            try:
                query = sql_text(f"""
                    SELECT * FROM {table_name} 
                    WHERE user_id = :user_id
                    ORDER BY name
                """)
                
                result = await session.execute(query, {"user_id": user.id})
                rows = result.fetchall()
                
                # Converti le righe in oggetti Wine
                wines = []
                for row in rows:
                    wine_dict = {
                        'id': row.id,
                        'user_id': row.user_id,
                        'name': row.name,
                        'producer': row.producer,
                        'vintage': row.vintage,
                        'grape_variety': row.grape_variety,
                        'region': row.region,
                        'country': row.country,
                        'wine_type': row.wine_type,
                        'classification': row.classification,
                        'quantity': row.quantity,
                        'min_quantity': row.min_quantity if hasattr(row, 'min_quantity') else 0,
                        'cost_price': row.cost_price,
                        'selling_price': row.selling_price,
                        'alcohol_content': row.alcohol_content,
                        'description': row.description,
                        'notes': row.notes,
                        'created_at': row.created_at,
                        'updated_at': row.updated_at
                    }
                    
                    wine = Wine()
                    for key, value in wine_dict.items():
                        setattr(wine, key, value)
                    wines.append(wine)
                
                logger.info(f"Recuperati {len(wines)} vini da tabella dinamica per {telegram_id}/{user.business_name}")
                return wines
                
            except Exception as e:
                logger.error(f"Errore leggendo inventario da tabella dinamica {table_name}: {e}")
                # Fallback: prova vecchia tabella wines
                try:
                    result = await session.execute(
                        select(Wine).where(Wine.user_id == user.id)
                    )
                    return list(result.scalars().all())
                except Exception as fallback_error:
                    logger.error(f"Errore anche nel fallback vecchia tabella wines: {fallback_error}", exc_info=True)
                    return []
    
    async def search_wines(self, telegram_id: int, search_term: str, limit: int = 10) -> List[Wine]:
        """
        Cerca vini con ricerca fuzzy avanzata (async).
        """
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                logger.warning(f"User {telegram_id} non trovato o business_name mancante")
                return []
            
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            
            try:
                search_term_clean = search_term.strip().lower()
                # Versione senza accenti/apostrofi per match più robusto (es. saten -> Satèn)
                accent_from = "àáâäèéêëìíîïòóôöùúûüÀÁÂÄÈÉÊËÌÍÎÏÒÓÔÖÙÚÛÜ’ʼ'`´"
                accent_to   = "aaaaeeeeiiiioooouuuuAAAAEEEEIIIIOOOOUUUU"  # char extra in 'from' verranno rimossi
                # Costruisci pattern unaccented lato Python per coerenza
                def strip_accents(s: str) -> str:
                    trans = str.maketrans({
                        'à':'a','á':'a','â':'a','ä':'a','è':'e','é':'e','ê':'e','ë':'e',
                        'ì':'i','í':'i','î':'i','ï':'i','ò':'o','ó':'o','ô':'o','ö':'o',
                        'ù':'u','ú':'u','û':'u','ü':'u',
                        'À':'A','Á':'A','Â':'A','Ä':'A','È':'E','É':'E','Ê':'E','Ë':'E',
                        'Ì':'I','Í':'I','Î':'I','Ï':'I','Ò':'O','Ó':'O','Ô':'O','Ö':'O',
                        'Ù':'U','Ú':'U','Û':'U','Ü':'U',
                        '’':'','ʼ':'','\'':'','`':'','´':''
                    })
                    return s.translate(trans)
                search_term_unaccent = strip_accents(search_term_clean)
                
                # Normalizza plurali italiani per uvaggi e nomi
                # Es: "vermentini" -> "vermentino", "spumanti" -> "spumante"
                def normalize_plural_for_search(term: str) -> list[str]:
                    """Ritorna lista di varianti: originale, senza plurale, con -o finale (per maschili)"""
                    variants = [term]
                    if len(term) > 2:
                        if term.endswith('i'):
                            # Plurale maschile: "vermentini" -> "vermentino"
                            base = term[:-1]
                            variants.append(base + 'o')  # vermentino
                            variants.append(base)  # vermentin (match parziale)
                        elif term.endswith('e'):
                            # Plurale femminile o altro: "bianche" -> "bianco"
                            base = term[:-1]
                            variants.append(base + 'a')  # bianca
                            variants.append(base + 'o')  # bianco
                            variants.append(base)  # bianch
                    return list(set(variants))  # Rimuovi duplicati
                
                search_variants = normalize_plural_for_search(search_term_clean)
                
                # Parole comuni italiane da ignorare per matching significativo
                stop_words = {'del', 'della', 'dello', 'dei', 'degli', 'delle', 'di', 'da', 'dal', 'dalla', 
                             'dallo', 'dai', 'dagli', 'dalle', 'la', 'le', 'il', 'lo', 'gli', 'i', 'un', 
                             'una', 'uno', 'e', 'o', 'a', 'in', 'su', 'per', 'con', 'tra', 'fra'}
                
                # Estrai parole significative (lunghe > 2 caratteri e non stop words)
                all_words = [w.strip() for w in search_term_clean.split()]
                search_words = [w for w in all_words if len(w) > 2 and w not in stop_words]
                
                # Determina se la query sembra essere un produttore
                # Criteri: contiene "del", "di", "da" O inizia con "ca" (es. "ca del bosco")
                is_likely_producer = any(word in search_term_clean for word in [' del ', ' di ', ' da ', 'ca ', 'ca\'', 'castello', 'tenuta', 'azienda'])
                
                # Determina se il termine è numerico (deve essere fatto PRIMA di usarlo)
                search_numeric = None
                search_float = None
                try:
                    search_numeric = int(search_term_clean)
                except ValueError:
                    try:
                        search_float = float(search_term_clean.replace(',', '.'))
                    except ValueError:
                        pass
                
                # Determina se la query è probabilmente un nome di uvaggio
                # Criteri: singola parola (o parole legate da apostrofo/trattino), non produttore, non numerico
                # Uvaggi italiani comuni (lista parziale)
                common_grape_varieties = {
                    'vermentino', 'nero', 'davola', 'nero d\'avola', 'nerodavola',
                    'sangiovese', 'montepulciano', 'barbera', 'nebbiolo', 'dolcetto',
                    'pinot', 'pinot grigio', 'pinot nero', 'pinot bianco',
                    'chardonnay', 'sauvignon', 'cabernet', 'merlot', 'syrah', 'shiraz',
                    'prosecco', 'glera', 'moscato', 'corvina', 'rondinella',
                    'garganega', 'trebbiano', 'malvasia', 'canaiolo', 'colorino',
                    'fiano', 'greco', 'falanghina', 'aglianico', 'primitivo', 'negroamaro',
                    'frapatto', 'nerello', 'carricante', 'catarratto', 'inzolia',
                    'gewurztraminer', 'gewurtzraminer', 'riesling', 'traminer',
                    'garnacha', 'tempranillo', 'grenache', 'mourvedre'
                }
                # Normalizza il termine per confronto (rimuovi apostrofi/spazi)
                search_normalized = search_term_clean.replace(' ', '').replace('\'', '').replace('-', '')
                is_likely_grape_variety = (
                    not is_likely_producer and 
                    search_numeric is None and 
                    search_float is None and
                    (search_term_clean in common_grape_varieties or 
                     search_normalized in common_grape_varieties or
                     any(gv in search_term_clean for gv in common_grape_varieties if len(gv) >= 6))
                )
                
                search_pattern = f"%{search_term_clean}%"
                search_pattern_unaccent = f"%{search_term_unaccent}%"
                
                # Condizioni base: match completo su frase (priorità alta)
                # Include anche grape_variety (uvaggio) per trovare vini cercando per vitigno
                # Aggiungi anche varianti plurali per gestire "vermentini" -> "vermentino"
                query_conditions = [
                    "name ILIKE :search_pattern",
                    "producer ILIKE :search_pattern",
                    "grape_variety ILIKE :search_pattern",
                    "translate(lower(name), :accent_from, :accent_to) ILIKE :search_pattern_unaccent",
                    "translate(lower(producer), :accent_from, :accent_to) ILIKE :search_pattern_unaccent",
                    "translate(lower(grape_variety), :accent_from, :accent_to) ILIKE :search_pattern_unaccent"
                ]
                
                # Aggiungi condizioni per varianti plurali (es. "vermentini" -> "vermentino")
                # Prepara anche i parametri da aggiungere a query_params
                variant_params = {}
                for idx, variant in enumerate(search_variants[1:], start=1):  # Skip primo (originale)
                    variant_pattern = f"%{variant}%"
                    variant_unaccent = strip_accents(variant)
                    variant_pattern_unaccent = f"%{variant_unaccent}%"
                    query_conditions.extend([
                        f"name ILIKE :search_variant_{idx}",
                        f"grape_variety ILIKE :search_variant_{idx}",
                        f"translate(lower(name), :accent_from, :accent_to) ILIKE :search_variant_unaccent_{idx}",
                        f"translate(lower(grape_variety), :accent_from, :accent_to) ILIKE :search_variant_unaccent_{idx}"
                    ])
                    variant_params[f"search_variant_{idx}"] = variant_pattern
                    variant_params[f"search_variant_unaccent_{idx}"] = variant_pattern_unaccent
                
                # Se ci sono parole significative, aggiungi condizioni più specifiche
                producer_name_split_params = {}  # Parametri per split producer/name (se necessario)
                if len(search_words) > 0:
                    # Per query multi-parola significative, richiediamo che TUTTE le parole significative matchino
                    if len(search_words) > 1:
                        # Costruisci condizione AND: tutte le parole significative devono essere presenti
                        if is_likely_producer:
                            # Per produttori, strategia più flessibile:
                            # 1. Match completo del termine nel producer (priorità alta)
                            # 2. Producer contiene le prime N parole (probabilmente nome produttore) 
                            #    AND name contiene le parole rimanenti (probabilmente nome vino specifico)
                            # 3. Tutte le parole insieme nel name (fallback)
                            
                            # Condizione 1: Match completo nel producer
                            query_conditions.append("producer ILIKE :search_pattern")
                            
                            # Condizione 2: Produttore + nome vino (più flessibile)
                            # Se abbiamo almeno 3 parole, prova a dividere: prime parole = produttore, ultime = nome
                            if len(search_words) >= 3:
                                # Usa le prime 2-3 parole per il produttore, le restanti per il nome
                                producer_words = search_words[:min(3, len(search_words)-1)]  # Almeno 1 parola per il nome
                                name_words = search_words[len(producer_words):]
                                
                                producer_conditions = [f"producer ILIKE :producer_word_{i}" for i in range(len(producer_words))]
                                name_conditions = [f"name ILIKE :name_word_{i}" for i in range(len(name_words))]
                                
                                # Salva i parametri da aggiungere dopo
                                for i, word in enumerate(producer_words):
                                    producer_name_split_params[f"producer_word_{i}"] = f"%{word}%"
                                for i, word in enumerate(name_words):
                                    producer_name_split_params[f"name_word_{i}"] = f"%{word}%"
                                
                                query_conditions.append(f"({' AND '.join(producer_conditions)} AND {' AND '.join(name_conditions)})")
                            
                            # Condizione 3: Tutte le parole nel producer (match completo)
                            word_conditions_producer = [f"producer ILIKE :word_{i}" for i in range(len(search_words))]
                            query_conditions.append(f"({' AND '.join(word_conditions_producer)})")
                            
                            # Condizione 4: Tutte le parole nel name (fallback)
                            word_conditions_name = [f"name ILIKE :word_{i}" for i in range(len(search_words))]
                            query_conditions.append(f"({' AND '.join(word_conditions_name)})")
                            
                            # Aggiungi i parametri split dopo la creazione di query_params (vedi sotto)
                        else:
                            # Per altre query, tutte le parole devono matchare (name O producer O grape_variety insieme)
                            word_conditions_combined = []
                            for i, word in enumerate(search_words):
                                word_variants = normalize_plural_for_search(word)
                                # Crea condizioni per ogni variante della parola
                                word_conditions = []
                                for j, variant in enumerate(word_variants):
                                    if j == 0:
                                        word_conditions.append(f"(name ILIKE :word_{i} OR producer ILIKE :word_{i} OR grape_variety ILIKE :word_{i})")
                                    else:
                                        param_key = f"word_{i}_var_{j}"
                                        word_conditions.append(f"(name ILIKE :{param_key} OR producer ILIKE :{param_key} OR grape_variety ILIKE :{param_key})")
                                word_conditions_combined.append(f"({' OR '.join(word_conditions)})")
                            query_conditions.append(f"({' AND '.join(word_conditions_combined)})")
                    else:
                        # Singola parola significativa: match più permissivo ma filtrato
                        word = search_words[0]
                        if is_likely_producer:
                            # Per produttori, cerca principalmente nel producer
                            query_conditions.extend([
                                f"producer ILIKE :word_0",
                                f"name ILIKE :word_0",
                                f"grape_variety ILIKE :word_0"
                            ])
                        else:
                            # Per singola parola, aggiungi anche varianti plurali
                            word_variants = normalize_plural_for_search(word)
                            query_conditions.append(f"(name ILIKE :word_0 OR producer ILIKE :word_0 OR grape_variety ILIKE :word_0)")
                            # Aggiungi condizioni per varianti (prepara parametri che verranno aggiunti dopo)
                            for j, variant in enumerate(word_variants[1:], start=1):
                                param_key = f"word_0_var_{j}"
                                query_conditions.append(f"(name ILIKE :{param_key} OR producer ILIKE :{param_key} OR grape_variety ILIKE :{param_key})")
                            # I parametri verranno aggiunti più avanti insieme alle altre varianti
                
                query_params = {
                    "user_id": user.id,
                    "search_pattern": search_pattern,
                    "search_pattern_unaccent": search_pattern_unaccent,
                    "accent_from": accent_from,
                    "accent_to": accent_to,
                    "limit": limit * 2  # Recupera più risultati per filtraggio post-query
                }
                
                # Aggiungi parametri per le parole significative e le loro varianti plurali
                for i, word in enumerate(search_words):
                    query_params[f"word_{i}"] = f"%{word}%"
                    # Aggiungi anche parametri per varianti plurali di ogni parola
                    word_variants = normalize_plural_for_search(word)
                    for j, variant in enumerate(word_variants[1:], start=1):
                        param_key = f"word_{i}_var_{j}"
                        query_params[param_key] = f"%{variant}%"
                
                # Aggiungi parametri per split producer/name (se presenti)
                query_params.update(producer_name_split_params)
                
                if search_numeric is not None:
                    query_conditions.append("vintage = :search_numeric")
                    query_params["search_numeric"] = search_numeric
                
                if search_float is not None:
                    query_conditions.append("(ABS(cost_price - :search_float) < 0.01 OR ABS(selling_price - :search_float) < 0.01)")
                    query_conditions.append("(ABS(alcohol_content - :search_float) < 0.1)")
                    query_params["search_float"] = search_float
                
                # Priorità uniforme: nome, produttore e uvaggio hanno la stessa priorità
                # Se il termine matcha in ALMENO UNO dei 3 campi, il vino viene incluso
                priority_case = """
                    CASE 
                        WHEN name ILIKE :search_pattern THEN 1
                        WHEN translate(lower(name), :accent_from, :accent_to) ILIKE :search_pattern_unaccent THEN 1
                        WHEN producer ILIKE :search_pattern THEN 1
                        WHEN translate(lower(producer), :accent_from, :accent_to) ILIKE :search_pattern_unaccent THEN 1
                        WHEN grape_variety ILIKE :search_pattern THEN 1
                        WHEN translate(lower(grape_variety), :accent_from, :accent_to) ILIKE :search_pattern_unaccent THEN 1
                        ELSE 2
                    END
                """
                
                query = sql_text(f"""
                    SELECT *, 
                        {priority_case} as match_priority
                    FROM {table_name} 
                    WHERE user_id = :user_id
                    AND ({' OR '.join(query_conditions)})
                    ORDER BY match_priority ASC, name ASC
                    LIMIT :limit
                """)
                
                result = await session.execute(query, query_params)
                rows = result.fetchall()
                
                wines = []
                search_term_lower = search_term_clean.lower()
                
                for row in rows:
                    wine_dict = {
                        'id': row.id,
                        'user_id': row.user_id,
                        'name': row.name,
                        'producer': row.producer,
                        'vintage': row.vintage,
                        'grape_variety': row.grape_variety,
                        'region': row.region,
                        'country': row.country,
                        'wine_type': row.wine_type,
                        'classification': row.classification,
                        'quantity': row.quantity,
                        'min_quantity': row.min_quantity if hasattr(row, 'min_quantity') else 0,
                        'cost_price': row.cost_price,
                        'selling_price': row.selling_price,
                        'alcohol_content': row.alcohol_content,
                        'description': row.description,
                        'notes': row.notes,
                        'created_at': row.created_at,
                        'updated_at': row.updated_at
                    }
                    
                    # Se il termine matcha in almeno uno dei 3 campi (name, producer, grape_variety), 
                    # il vino viene incluso - nessun filtro post-query per escludere risultati validi
                    
                    wine = Wine()
                    for key, value in wine_dict.items():
                        setattr(wine, key, value)
                    wines.append(wine)
                
                # Limita i risultati finali
                wines = wines[:limit]
                
                logger.info(f"Trovati {len(wines)} vini per ricerca '{search_term}' per {telegram_id}/{user.business_name} (is_producer={is_likely_producer}, words={search_words})")
                return wines
                
            except Exception as e:
                logger.error(f"Errore ricerca vini da tabella dinamica {table_name}: {e}")
                return []
    
    async def get_inventory_logs(self, telegram_id: int, limit: int = 50):
        """Ottieni log inventario dalla tabella dinamica LOG interazione (async)"""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return []

    async def log_chat_message(self, telegram_id: int, role: str, content: str) -> bool:
        """Registra un messaggio di chat nella tabella dinamica LOG interazione."""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return False
            table_name = f'"{telegram_id}/{user.business_name} LOG interazione"'
            try:
                # Normalizza ruolo su tipi ammessi
                interaction_type = 'chat_user' if role == 'user' or role == 'chat_user' else 'chat_assistant'
                insert_query = sql_text(f"""
                    INSERT INTO {table_name}
                    (user_id, interaction_type, interaction_data, created_at)
                    VALUES (:user_id, :interaction_type, :interaction_data, CURRENT_TIMESTAMP)
                """)
                await session.execute(insert_query, {
                    "user_id": user.id,
                    "interaction_type": interaction_type,
                    "interaction_data": content[:8000] if content else None
                })
                await session.commit()
                return True
            except Exception as e:
                logger.error(f"Errore salvando chat log in {table_name}: {e}")
                await session.rollback()
                return False

    async def get_recent_chat_messages(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Recupera ultimi messaggi chat (utente/assistant) dalla tabella LOG interazione."""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return []
            table_name = f'"{telegram_id}/{user.business_name} LOG interazione"'
            try:
                query = sql_text(f"""
                    SELECT interaction_type, interaction_data, created_at
                    FROM {table_name}
                    WHERE user_id = :user_id
                      AND interaction_type IN ('chat_user','chat_assistant')
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                result = await session.execute(query, {"user_id": user.id, "limit": limit})
                rows = result.fetchall()
                history = []
                for row in rows:
                    role = 'user' if row.interaction_type == 'chat_user' else 'assistant'
                    history.append({
                        "role": role,
                        "content": row.interaction_data or "",
                        "created_at": row.created_at
                    })
                # Ritorna in ordine cronologico (dal più vecchio al più recente)
                history.reverse()
                return history
            except Exception as e:
                logger.error(f"Errore leggendo chat history da {table_name}: {e}")
                return []
            
            table_name = f'"{telegram_id}/{user.business_name} LOG interazione"'
            
            try:
                query = sql_text(f"""
                    SELECT * FROM {table_name} 
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """)
                
                result = await session.execute(query, {
                    "user_id": user.id,
                    "limit": limit
                })
                rows = result.fetchall()
                
                logs = []
                for row in rows:
                    log_dict = {
                        'id': row.id if hasattr(row, 'id') else None,
                        'message': row.message if hasattr(row, 'message') else str(row),
                        'created_at': row.created_at if hasattr(row, 'created_at') else None
                    }
                    logs.append(log_dict)
                
                return logs
            except Exception as e:
                logger.error(f"Errore leggendo log da tabella dinamica {table_name}: {e}")
                return []
    
    async def get_movement_logs(self, telegram_id: int, limit: int = 50):
        """Ottieni log movimenti dalla tabella 'Consumi e rifornimenti' (async)"""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return []
            
            table_name = f'"{telegram_id}/{user.business_name} Consumi e rifornimenti"'
            
            try:
                query = sql_text(f"""
                    SELECT * FROM {table_name} 
                    WHERE user_id = :user_id
                    ORDER BY movement_date DESC
                    LIMIT :limit
                """)
                
                result = await session.execute(query, {
                    "user_id": user.id,
                    "limit": limit
                })
                rows = result.fetchall()
                
                logs = []
                for row in rows:
                    # Usa nuovo schema: wine_name, movement_type, quantity_change, movement_date
                    log_dict = {
                        'id': getattr(row, 'id', None),
                        'wine_name': getattr(row, 'wine_name', None),
                        'wine_producer': getattr(row, 'wine_producer', None),
                        'movement_type': getattr(row, 'movement_type', None),
                        'quantity_change': getattr(row, 'quantity_change', 0),
                        'quantity_before': getattr(row, 'quantity_before', 0),
                        'quantity_after': getattr(row, 'quantity_after', 0),
                        'movement_date': getattr(row, 'movement_date', None),
                        'notes': getattr(row, 'notes', None)
                    }
                    logs.append(log_dict)
                
                return logs
            except Exception as e:
                logger.error(f"Errore leggendo movimenti da tabella dinamica {table_name}: {e}")
                return []
    
    async def add_wine(self, telegram_id: int, wine_data: Dict[str, Any]) -> Optional[Wine]:
        """Aggiungi un vino all'inventario (alle tabelle dinamiche)"""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                logger.warning(f"User {telegram_id} non trovato o business_name mancante")
                return None
            
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            
            try:
                # Prepara valori per INSERT
                insert_query = sql_text(f"""
                    INSERT INTO {table_name} 
                    (user_id, name, producer, vintage, grape_variety, region, country, 
                     wine_type, classification, quantity, min_quantity, cost_price, 
                     selling_price, alcohol_content, description, notes, created_at, updated_at)
                    VALUES 
                    (:user_id, :name, :producer, :vintage, :grape_variety, :region, :country,
                     :wine_type, :classification, :quantity, :min_quantity, :cost_price,
                     :selling_price, :alcohol_content, :description, :notes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id, name, producer, vintage, grape_variety, region, country,
                              wine_type, classification, quantity, min_quantity, cost_price,
                              selling_price, alcohol_content, description, notes, created_at, updated_at
                """)
                
                result = await session.execute(insert_query, {
                    "user_id": user.id,
                    "name": wine_data.get('name', ''),
                    "producer": wine_data.get('producer'),
                    "vintage": wine_data.get('vintage'),
                    "grape_variety": wine_data.get('grape_variety'),
                    "region": wine_data.get('region'),
                    "country": wine_data.get('country'),
                    "wine_type": wine_data.get('wine_type'),
                    "classification": wine_data.get('classification'),
                    "quantity": wine_data.get('quantity', 0),
                    "min_quantity": wine_data.get('min_quantity', 0),
                    "cost_price": wine_data.get('cost_price'),
                    "selling_price": wine_data.get('selling_price'),
                    "alcohol_content": wine_data.get('alcohol_content'),
                    "description": wine_data.get('description'),
                    "notes": wine_data.get('notes')
                })
                
                await session.commit()
                row = result.fetchone()
                
                if row:
                    wine = Wine()
                    for key in ['id', 'user_id', 'name', 'producer', 'vintage', 'grape_variety',
                               'region', 'country', 'wine_type', 'classification', 'quantity',
                               'min_quantity', 'cost_price', 'selling_price', 'alcohol_content',
                               'description', 'notes', 'created_at', 'updated_at']:
                        if hasattr(row, key):
                            setattr(wine, key, getattr(row, key))
                    logger.info(f"Vino aggiunto: {wine.name} per utente {telegram_id}")
                    return wine
                return None
            except Exception as e:
                logger.error(f"Errore aggiungendo vino: {e}")
                await session.rollback()
                return None
    
    async def get_low_stock_wines(self, telegram_id: int) -> List[Wine]:
        """Ottieni vini con scorta bassa (quantity <= min_quantity)"""
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return []
            
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            
            try:
                query = sql_text(f"""
                    SELECT * FROM {table_name} 
                    WHERE user_id = :user_id
                      AND (quantity IS NULL OR quantity <= COALESCE(min_quantity, 0))
                    ORDER BY name
                """)
                
                result = await session.execute(query, {"user_id": user.id})
                rows = result.fetchall()
                
                # Converti le righe in oggetti Wine
                wines = []
                for row in rows:
                    wine = Wine()
                    for key in ['id', 'user_id', 'name', 'producer', 'vintage', 'grape_variety',
                               'region', 'country', 'wine_type', 'classification', 'quantity',
                               'min_quantity', 'cost_price', 'selling_price', 'alcohol_content',
                               'description', 'notes', 'created_at', 'updated_at']:
                        if hasattr(row, key):
                            setattr(wine, key, getattr(row, key))
                    wines.append(wine)
                
                return wines
            except Exception as e:
                logger.error(f"Errore recuperando low stock wines da {table_name}: {e}")
                return []

    async def search_wines_filtered(self, telegram_id: int, filters: Dict[str, Any], limit: int = 50, offset: int = 0) -> List[Wine]:
        """
        Ricerca con filtri multipli. Filtri supportati: region, country, producer, wine_type, classification,
        name_contains, vintage_min, vintage_max, price_min, price_max, cost_price_min, cost_price_max, quantity_min, quantity_max.
        """
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return []
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            clauses = ["user_id = :user_id"]
            params = {"user_id": user.id, "limit": limit, "offset": offset}

            def normalize_plural(word: str) -> str:
                """Normalizza plurali italiani comuni per matching più permissivo"""
                if not word:
                    return word
                word_lower = word.lower().strip()
                # Rimuovi suffissi plurali comuni italiani
                if word_lower.endswith('i'):
                    # es. "spumanti" -> "spumant", "rossi" -> "ross"
                    return word_lower[:-1]
                elif word_lower.endswith('e'):
                    # es. "bianche" -> "bianch"
                    return word_lower[:-1]
                return word_lower

            def add_ilike(field, value):
                if value:
                    # Normalizza per gestire plurali (es. "vermentini" matcha "vermentino")
                    variants = normalize_plural(value)
                    
                    # Crea condizioni OR per tutte le varianti
                    variant_conditions = []
                    for idx, variant in enumerate(variants):
                        param_key = f"{field}_var_{idx}" if idx > 0 else f"{field}_exact"
                        variant_conditions.append(f"{field} ILIKE :{param_key}")
                        params[param_key] = f"%{variant}%"
                    
                    # Se solo una variante (originale), usa sintassi semplice
                    if len(variant_conditions) == 1:
                        clauses.append(f"{field} ILIKE :{field}_exact")
                    else:
                        clauses.append(f"({' OR '.join(variant_conditions)})")

            add_ilike("region", filters.get("region"))
            add_ilike("country", filters.get("country"))
            add_ilike("producer", filters.get("producer"))
            add_ilike("wine_type", filters.get("wine_type"))
            add_ilike("classification", filters.get("classification"))
            if filters.get("name_contains"):
                # Cerca in name, producer e grape_variety quando si usa name_contains
                clauses.append("(name ILIKE :name_contains OR producer ILIKE :name_contains OR grape_variety ILIKE :name_contains)")
                params["name_contains"] = f"%{filters['name_contains']}%"

            # Range numerici
            if filters.get("vintage_min") is not None:
                clauses.append("vintage >= :vintage_min")
                params["vintage_min"] = int(filters["vintage_min"])
            if filters.get("vintage_max") is not None:
                clauses.append("vintage <= :vintage_max")
                params["vintage_max"] = int(filters["vintage_max"])
            if filters.get("price_min") is not None:
                clauses.append("selling_price >= :price_min")
                params["price_min"] = float(filters["price_min"])
            if filters.get("price_max") is not None:
                clauses.append("selling_price <= :price_max")
                params["price_max"] = float(filters["price_max"])
            if filters.get("cost_price_min") is not None:
                clauses.append("cost_price >= :cost_price_min")
                params["cost_price_min"] = float(filters["cost_price_min"])
            if filters.get("cost_price_max") is not None:
                clauses.append("cost_price <= :cost_price_max")
                params["cost_price_max"] = float(filters["cost_price_max"])
            if filters.get("quantity_min") is not None:
                clauses.append("quantity >= :quantity_min")
                params["quantity_min"] = int(filters["quantity_min"])
            if filters.get("quantity_max") is not None:
                clauses.append("quantity <= :quantity_max")
                params["quantity_max"] = int(filters["quantity_max"])

            where_sql = " AND ".join(clauses)
            query = sql_text(f"""
                SELECT * FROM {table_name}
                WHERE {where_sql}
                ORDER BY name ASC
                LIMIT :limit OFFSET :offset
            """)
            try:
                result = await session.execute(query, params)
                rows = result.fetchall()
                wines = []
                for row in rows:
                    wine = Wine()
                    for key in ['id', 'user_id', 'name', 'producer', 'vintage', 'grape_variety',
                               'region', 'country', 'wine_type', 'classification', 'quantity',
                               'min_quantity', 'cost_price', 'selling_price', 'alcohol_content',
                               'description', 'notes', 'created_at', 'updated_at']:
                        if hasattr(row, key):
                            setattr(wine, key, getattr(row, key))
                    wines.append(wine)
                return wines
            except Exception as e:
                logger.error(f"Errore search_wines_filtered su {table_name}: {e}")
                return []

    async def get_inventory_stats(self, telegram_id: int) -> Dict[str, Any]:
        """
        Statistiche inventario: totale vini, totale bottiglie, min/max/avg prezzo, low stock.
        """
        async with await get_async_session() as session:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user or not user.business_name:
                return {"total_wines": 0, "total_bottles": 0, "avg_price": None, "min_price": None, "max_price": None, "low_stock": 0}
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            try:
                stats_q = sql_text(f"""
                    SELECT 
                      COUNT(*) AS total_wines,
                      COALESCE(SUM(COALESCE(quantity,0)),0) AS total_bottles,
                      AVG(selling_price) AS avg_price,
                      MIN(selling_price) AS min_price,
                      MAX(selling_price) AS max_price,
                      SUM(CASE WHEN COALESCE(quantity,0) <= COALESCE(min_quantity,0) THEN 1 ELSE 0 END) AS low_stock
                    FROM {table_name}
                    WHERE user_id = :user_id
                """)
                res = await session.execute(stats_q, {"user_id": user.id})
                row = res.fetchone()
                return {
                    "total_wines": int(row.total_wines) if row and hasattr(row,'total_wines') else 0,
                    "total_bottles": int(row.total_bottles) if row and hasattr(row,'total_bottles') else 0,
                    "avg_price": float(row.avg_price) if row and getattr(row,'avg_price', None) is not None else None,
                    "min_price": float(row.min_price) if row and getattr(row,'min_price', None) is not None else None,
                    "max_price": float(row.max_price) if row and getattr(row,'max_price', None) is not None else None,
                    "low_stock": int(row.low_stock) if row and hasattr(row,'low_stock') else 0,
                }
            except Exception as e:
                logger.error(f"Errore get_inventory_stats su {table_name}: {e}", exc_info=True)
                return {"total_wines": 0, "total_bottles": 0, "avg_price": None, "min_price": None, "max_price": None, "low_stock": 0}
            
            table_name = f'"{telegram_id}/{user.business_name} INVENTARIO"'
            
            try:
                query = sql_text(f"""
                    SELECT * FROM {table_name} 
                    WHERE user_id = :user_id
                    AND quantity <= COALESCE(min_quantity, 0)
                    ORDER BY name
                """)
                
                result = await session.execute(query, {"user_id": user.id})
                rows = result.fetchall()
                
                wines = []
                for row in rows:
                    wine = Wine()
                    for key in ['id', 'user_id', 'name', 'producer', 'vintage', 'grape_variety',
                               'region', 'country', 'wine_type', 'classification', 'quantity',
                               'min_quantity', 'cost_price', 'selling_price', 'alcohol_content',
                               'description', 'notes', 'created_at', 'updated_at']:
                        if hasattr(row, key):
                            setattr(wine, key, getattr(row, key))
                    wines.append(wine)
                
                return wines
            except Exception as e:
                logger.error(f"Errore recuperando scorte basse: {e}", exc_info=True)
                return []


# Istanza globale
async_db_manager = AsyncDatabaseManager()


# Utility per cutoff periodo
async def _compute_cutoff(period: str):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if period == 'week':
        return now - timedelta(days=7)
    if period == 'month':
        return now - timedelta(days=30)
    return now - timedelta(days=1)




async def get_movement_summary_yesterday(telegram_id: int) -> Dict[str, Any]:
    """
    Riepiloga movimenti di ieri (giorno precedente).
    Ritorna dizionario con totali e top prodotti.
    """
    from datetime import datetime, timedelta
    async with await get_async_session() as session:
        # Carica utente
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user or not user.business_name:
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}
        
        table_name = f'"{telegram_id}/{user.business_name} Consumi e rifornimenti"'
        
        # Calcola ieri: inizio e fine del giorno precedente
        now = datetime.utcnow()
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)
        
        try:
            totals_q = sql_text(f"""
                SELECT 
                  COALESCE(SUM(CASE WHEN movement_type = 'consumo' THEN ABS(quantity_change) ELSE 0 END), 0) AS total_consumed,
                  COALESCE(SUM(CASE WHEN movement_type = 'rifornimento' THEN quantity_change ELSE 0 END), 0) AS total_replenished
                FROM {table_name}
                WHERE user_id = :user_id 
                AND movement_date >= :yesterday_start 
                AND movement_date < :yesterday_end
            """)
            res = await session.execute(totals_q, {
                "user_id": user.id, 
                "yesterday_start": yesterday_start, 
                "yesterday_end": yesterday_end
            })
            row = res.fetchone()
            total_consumed = int(row.total_consumed) if row and hasattr(row, 'total_consumed') else 0
            total_replenished = int(row.total_replenished) if row and hasattr(row, 'total_replenished') else 0

            top_c_q = sql_text(f"""
                SELECT wine_name AS name, COALESCE(SUM(ABS(quantity_change)), 0) AS qty
                FROM {table_name}
                WHERE user_id = :user_id 
                AND movement_date >= :yesterday_start 
                AND movement_date < :yesterday_end
                AND movement_type = 'consumo'
                GROUP BY wine_name
                HAVING COALESCE(SUM(ABS(quantity_change)), 0) > 0
                ORDER BY qty DESC
                LIMIT 5
            """)
            res_c = await session.execute(top_c_q, {
                "user_id": user.id, 
                "yesterday_start": yesterday_start, 
                "yesterday_end": yesterday_end
            })
            top_consumed = [(r.name, int(r.qty)) for r in res_c.fetchall()]

            top_r_q = sql_text(f"""
                SELECT wine_name AS name, COALESCE(SUM(quantity_change), 0) AS qty
                FROM {table_name}
                WHERE user_id = :user_id 
                AND movement_date >= :yesterday_start 
                AND movement_date < :yesterday_end
                AND movement_type = 'rifornimento'
                GROUP BY wine_name
                HAVING COALESCE(SUM(quantity_change), 0) > 0
                ORDER BY qty DESC
                LIMIT 5
            """)
            res_r = await session.execute(top_r_q, {
                "user_id": user.id, 
                "yesterday_start": yesterday_start, 
                "yesterday_end": yesterday_end
            })
            top_replenished = [(r.name, int(r.qty)) for r in res_r.fetchall()]

            return {
                "total_consumed": total_consumed,
                "total_replenished": total_replenished,
                "net_change": int(total_replenished - total_consumed),
                "top_consumed": top_consumed,
                "top_replenished": top_replenished,
            }
        except Exception as e:
            logger.error(f"Errore riepilogo movimenti ieri da tabella {table_name}: {e}", exc_info=True)
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}


async def get_movement_summary_yesterday_replenished(telegram_id: int) -> Dict[str, Any]:
    """
    Riepiloga SOLO rifornimenti di ieri (giorno precedente).
    Ritorna dizionario con totali e top prodotti riforniti.
    """
    from datetime import datetime, timedelta
    async with await get_async_session() as session:
        # Carica utente
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user or not user.business_name:
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}
        
        table_name = f'"{telegram_id}/{user.business_name} Consumi e rifornimenti"'
        
        # Calcola ieri: inizio e fine del giorno precedente
        now = datetime.utcnow()
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)
        
        try:
            # Solo rifornimenti (total_consumed = 0)
            totals_q = sql_text(f"""
                SELECT 
                  0 AS total_consumed,
                  COALESCE(SUM(CASE WHEN movement_type = 'rifornimento' THEN quantity_change ELSE 0 END), 0) AS total_replenished
                FROM {table_name}
                WHERE user_id = :user_id 
                AND movement_date >= :yesterday_start 
                AND movement_date < :yesterday_end
                AND movement_type = 'rifornimento'
            """)
            res = await session.execute(totals_q, {
                "user_id": user.id, 
                "yesterday_start": yesterday_start, 
                "yesterday_end": yesterday_end
            })
            row = res.fetchone()
            total_replenished = int(row.total_replenished) if row and hasattr(row, 'total_replenished') else 0

            # Top riforniti
            top_r_q = sql_text(f"""
                SELECT wine_name AS name, COALESCE(SUM(quantity_change), 0) AS qty
                FROM {table_name}
                WHERE user_id = :user_id 
                AND movement_date >= :yesterday_start 
                AND movement_date < :yesterday_end
                AND movement_type = 'rifornimento'
                GROUP BY wine_name
                HAVING COALESCE(SUM(quantity_change), 0) > 0
                ORDER BY qty DESC
                LIMIT 10
            """)
            res_r = await session.execute(top_r_q, {
                "user_id": user.id, 
                "yesterday_start": yesterday_start, 
                "yesterday_end": yesterday_end
            })
            top_replenished = [(r.name, int(r.qty)) for r in res_r.fetchall()]

            return {
                "total_consumed": 0,
                "total_replenished": total_replenished,
                "net_change": int(total_replenished),
                "top_consumed": [],  # Nessun consumo
                "top_replenished": top_replenished,
            }
        except Exception as e:
            logger.error(f"Errore riepilogo rifornimenti ieri da tabella {table_name}: {e}", exc_info=True)
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}


async def get_movement_summary(telegram_id: int, period: str = 'day') -> Dict[str, Any]:
    """
    Riepiloga movimenti (consumi/rifornimenti) per periodo: day/week/month.
    Ritorna dizionario con totali e top prodotti.
    """
    async with await get_async_session() as session:
        # Carica utente
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user or not user.business_name:
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}
        table_name = f'"{telegram_id}/{user.business_name} Consumi e rifornimenti"'
        cutoff = await _compute_cutoff(period)
        try:
            totals_q = sql_text(f"""
                SELECT 
                  COALESCE(SUM(CASE WHEN movement_type = 'consumo' THEN ABS(quantity_change) ELSE 0 END), 0) AS total_consumed,
                  COALESCE(SUM(CASE WHEN movement_type = 'rifornimento' THEN quantity_change ELSE 0 END), 0) AS total_replenished
                FROM {table_name}
                WHERE user_id = :user_id AND movement_date >= :cutoff
            """)
            res = await session.execute(totals_q, {"user_id": user.id, "cutoff": cutoff})
            row = res.fetchone()
            total_consumed = int(row.total_consumed) if row and hasattr(row, 'total_consumed') else 0
            total_replenished = int(row.total_replenished) if row and hasattr(row, 'total_replenished') else 0

            top_c_q = sql_text(f"""
                SELECT wine_name AS name, COALESCE(SUM(ABS(quantity_change)), 0) AS qty
                FROM {table_name}
                WHERE user_id = :user_id AND movement_date >= :cutoff AND movement_type = 'consumo'
                GROUP BY wine_name
                HAVING COALESCE(SUM(ABS(quantity_change)), 0) > 0
                ORDER BY qty DESC
                LIMIT 5
            """)
            res_c = await session.execute(top_c_q, {"user_id": user.id, "cutoff": cutoff})
            top_consumed = [(r.name, int(r.qty)) for r in res_c.fetchall()]

            top_r_q = sql_text(f"""
                SELECT wine_name AS name, COALESCE(SUM(quantity_change), 0) AS qty
                FROM {table_name}
                WHERE user_id = :user_id AND movement_date >= :cutoff AND movement_type = 'rifornimento'
                GROUP BY wine_name
                HAVING COALESCE(SUM(quantity_change), 0) > 0
                ORDER BY qty DESC
                LIMIT 5
            """)
            res_r = await session.execute(top_r_q, {"user_id": user.id, "cutoff": cutoff})
            top_replenished = [(r.name, int(r.qty)) for r in res_r.fetchall()]

            return {
                "total_consumed": total_consumed,
                "total_replenished": total_replenished,
                "net_change": int(total_replenished - total_consumed),
                "top_consumed": top_consumed,
                "top_replenished": top_replenished,
            }
        except Exception as e:
            logger.error(f"Errore riepilogo movimenti da tabella {table_name}: {e}", exc_info=True)
            return {"total_consumed": 0, "total_replenished": 0, "net_change": 0}

