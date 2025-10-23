"""
Database per il microservizio processor
Condivide lo stesso database del bot principale
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

logger = logging.getLogger(__name__)

# Base per i modelli SQLAlchemy
Base = declarative_base()

class User(Base):
    """Modello per gli utenti del bot"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
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
    
    # Relazioni
    wines = relationship("Wine", back_populates="user", cascade="all, delete-orphan")
    inventory_backups = relationship("InventoryBackup", back_populates="user", cascade="all, delete-orphan")
    inventory_logs = relationship("InventoryLog", back_populates="user", cascade="all, delete-orphan")

class Wine(Base):
    """Modello per l'inventario vini"""
    __tablename__ = 'wines'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati vino
    name = Column(String(200), nullable=False)
    producer = Column(String(200))
    vintage = Column(Integer)
    grape_variety = Column(String(200))
    region = Column(String(200))
    country = Column(String(100))
    
    # Classificazione
    wine_type = Column(String(50))
    classification = Column(String(100))
    
    # Quantità e prezzi
    quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=0)
    cost_price = Column(Float)
    selling_price = Column(Float)
    
    # Dettagli
    alcohol_content = Column(Float)
    description = Column(Text)
    notes = Column(Text)
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="wines")

class InventoryBackup(Base):
    """Backup dell'inventario"""
    __tablename__ = 'inventory_backups'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    backup_name = Column(String(200), nullable=False)
    backup_data = Column(Text, nullable=False)
    backup_type = Column(String(20), default="initial")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="inventory_backups")

class InventoryLog(Base):
    """Log di movimenti inventario"""
    __tablename__ = 'inventory_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    wine_name = Column(String(200), nullable=False)
    wine_producer = Column(String(200))
    movement_type = Column(String(20), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    quantity_before = Column(Integer, nullable=False)
    quantity_after = Column(Integer, nullable=False)
    
    notes = Column(Text)
    movement_date = Column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="inventory_logs")

class DatabaseManager:
    """Gestore del database PostgreSQL"""
    
    def __init__(self):
        # Usa DATABASE_URL da Railway PostgreSQL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            database_url = "postgresql://user:password@localhost/gioia_bot"
            logger.warning("DATABASE_URL non trovata, usando fallback locale")
        else:
            logger.info(f"DATABASE_URL trovata: {database_url[:20]}...")
        
        # Converte URL Railway in formato SQLAlchemy
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        
        try:
            self.engine = create_engine(database_url, echo=False)
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            # Test connessione
            with self.engine.connect() as conn:
                logger.info("Connessione database testata con successo")
            
            # Crea le tabelle se non esistono
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database PostgreSQL inizializzato e tabelle create")
            
        except Exception as e:
            logger.error(f"Errore inizializzazione database: {e}")
            self.engine = None
            self.SessionLocal = None
    
    def get_session(self) -> Session:
        """Ottieni una sessione del database"""
        if not self.SessionLocal:
            raise Exception("Database non inizializzato")
        return self.SessionLocal()
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Trova un utente per Telegram ID"""
        with self.get_session() as session:
            return session.query(User).filter(User.telegram_id == telegram_id).first()
    
    def get_user_wines(self, telegram_id: int) -> List[Wine]:
        """Ottieni tutti i vini di un utente"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return []
            return session.query(Wine).filter(Wine.user_id == user.id).all()
    
    def add_wine(self, telegram_id: int, wine_data: Dict[str, Any]) -> Optional[Wine]:
        """Aggiungi un vino all'inventario"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return None
            
            wine = Wine(user_id=user.id, **wine_data)
            session.add(wine)
            session.commit()
            session.refresh(wine)
            logger.info(f"Vino aggiunto per utente {telegram_id}: {wine.name}")
            return wine
    
    def get_user_stats(self, telegram_id: int) -> Dict[str, Any]:
        """Ottieni statistiche utente"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return {}
            
            wines = session.query(Wine).filter(Wine.user_id == user.id).all()
            
            total_wines = len(wines)
            total_quantity = sum(w.quantity for w in wines)
            low_stock_count = len([w for w in wines if w.quantity <= w.min_quantity])
            
            return {
                "total_wines": total_wines,
                "total_quantity": total_quantity,
                "low_stock_count": low_stock_count,
                "onboarding_completed": user.onboarding_completed
            }
    
    def create_inventory_backup(self, telegram_id: int, backup_name: str, backup_data: str, backup_type: str = "initial") -> bool:
        """Crea un backup dell'inventario"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return False
            
            backup = InventoryBackup(
                user_id=user.id,
                backup_name=backup_name,
                backup_data=backup_data,
                backup_type=backup_type
            )
            session.add(backup)
            session.commit()
            logger.info(f"Backup creato per utente {telegram_id}: {backup_name}")
            return True

# Istanza globale del database
db_manager = DatabaseManager()
