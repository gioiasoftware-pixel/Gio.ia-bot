"""
Database per Gio.ia-bot - Gestione utenti e inventario vini
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
    business_type = Column(String(100))  # enoteca, ristorante, bar, etc.
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
    vintage = Column(Integer)  # Annata
    grape_variety = Column(String(200))  # Vitigno
    region = Column(String(200))
    country = Column(String(100))
    
    # Classificazione
    wine_type = Column(String(50))  # rosso, bianco, rosato, spumante, etc.
    classification = Column(String(100))  # DOCG, DOC, IGT, etc.
    
    # Quantità e prezzi
    quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=0)  # Scorta minima
    cost_price = Column(Float)  # Prezzo di acquisto
    selling_price = Column(Float)  # Prezzo di vendita
    
    # Dettagli
    alcohol_content = Column(Float)  # Gradazione alcolica
    description = Column(Text)
    notes = Column(Text)
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="wines")

class InventoryBackup(Base):
    """Backup dell'inventario iniziale per ogni utente"""
    __tablename__ = 'inventory_backups'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati del backup
    backup_name = Column(String(200), nullable=False)  # "Inventario Iniziale", "Backup Giorno X"
    backup_data = Column(Text, nullable=False)  # JSON con tutti i dati inventario
    backup_type = Column(String(20), default="initial")  # 'initial', 'daily', 'manual'
    
    # Metadati
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relazioni
    user = relationship("User", back_populates="inventory_backups")

class InventoryLog(Base):
    """Log di consumi e rifornimenti per ogni utente"""
    __tablename__ = 'inventory_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Dati del movimento
    wine_name = Column(String(200), nullable=False)
    wine_producer = Column(String(200))
    movement_type = Column(String(20), nullable=False)  # 'consumo', 'rifornimento', 'aggiustamento'
    quantity_change = Column(Integer, nullable=False)  # Positivo per rifornimenti, negativo per consumi
    quantity_before = Column(Integer, nullable=False)  # Quantità prima del movimento
    quantity_after = Column(Integer, nullable=False)   # Quantità dopo il movimento
    
    # Dettagli
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
            # Fallback per sviluppo locale
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
            
            # Test connessione prima di creare tabelle
            with self.engine.connect() as conn:
                logger.info("Connessione database testata con successo")
            
            # Crea le tabelle se non esistono
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database PostgreSQL inizializzato e tabelle create")
            
        except Exception as e:
            logger.error(f"Errore inizializzazione database: {e}")
            # Crea engine di fallback per evitare crash
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
    
    def get_all_users(self) -> List[User]:
        """Ottieni tutti gli utenti"""
        with self.get_session() as session:
            return session.query(User).all()
    
    def create_user(self, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """Crea un nuovo utente"""
        with self.get_session() as session:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info(f"Nuovo utente creato: {user.telegram_id}")
            return user
    
    def update_user_onboarding(self, telegram_id: int, **kwargs) -> bool:
        """Aggiorna i dati di onboarding di un utente"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return False
            
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            user.updated_at = datetime.utcnow()
            session.commit()
            logger.info(f"Onboarding aggiornato per utente {telegram_id}")
            return True
    
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
    
    def update_wine_quantity(self, telegram_id: int, wine_id: int, new_quantity: int) -> bool:
        """Aggiorna la quantità di un vino"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return False
            
            wine = session.query(Wine).filter(Wine.id == wine_id, Wine.user_id == user.id).first()
            if not wine:
                return False
            
            wine.quantity = new_quantity
            wine.updated_at = datetime.utcnow()
            session.commit()
            logger.info(f"Quantità aggiornata per vino {wine_id}: {new_quantity}")
            return True
    
    def get_low_stock_wines(self, telegram_id: int) -> List[Wine]:
        """Ottieni vini con scorta bassa"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return []
            
            return session.query(Wine).filter(
                Wine.user_id == user.id,
                Wine.quantity <= Wine.min_quantity
            ).all()
    
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
    
    def add_inventory_log(self, telegram_id: int, wine_name: str, wine_producer: str, 
                         movement_type: str, quantity_change: int, quantity_before: int, 
                         quantity_after: int, notes: str = None) -> bool:
        """Aggiunge un log di movimento inventario"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return False
            
            log = InventoryLog(
                user_id=user.id,
                wine_name=wine_name,
                wine_producer=wine_producer,
                movement_type=movement_type,
                quantity_change=quantity_change,
                quantity_before=quantity_before,
                quantity_after=quantity_after,
                notes=notes
            )
            session.add(log)
            session.commit()
            logger.info(f"Log aggiunto per utente {telegram_id}: {movement_type} {wine_name}")
            return True
    
    def get_inventory_logs(self, telegram_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Ottieni i log di inventario di un utente"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return []
            
            logs = session.query(InventoryLog).filter(
                InventoryLog.user_id == user.id
            ).order_by(InventoryLog.movement_date.desc()).limit(limit).all()
            
            return [
                {
                    'id': log.id,
                    'wine_name': log.wine_name,
                    'wine_producer': log.wine_producer,
                    'movement_type': log.movement_type,
                    'quantity_change': log.quantity_change,
                    'quantity_before': log.quantity_before,
                    'quantity_after': log.quantity_after,
                    'notes': log.notes,
                    'movement_date': log.movement_date
                }
                for log in logs
            ]
    
    def update_wine_quantity_with_log(self, telegram_id: int, wine_name: str, 
                                    quantity_change: int, movement_type: str, notes: str = None) -> bool:
        """Aggiorna quantità vino e crea log"""
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return False
            
            # Trova il vino
            wine = session.query(Wine).filter(
                Wine.user_id == user.id,
                Wine.name.ilike(f"%{wine_name}%")
            ).first()
            
            if not wine:
                return False
            
            quantity_before = wine.quantity
            quantity_after = quantity_before + quantity_change
            
            # Aggiorna quantità
            wine.quantity = quantity_after
            wine.updated_at = datetime.utcnow()
            
            # Crea log
            log = InventoryLog(
                user_id=user.id,
                wine_name=wine.name,
                wine_producer=wine.producer,
                movement_type=movement_type,
                quantity_change=quantity_change,
                quantity_before=quantity_before,
                quantity_after=quantity_after,
                notes=notes
            )
            session.add(log)
            session.commit()
            
            logger.info(f"Quantità aggiornata per {wine.name}: {quantity_before} -> {quantity_after}")
            return True

# Istanza globale del database
db_manager = DatabaseManager()
