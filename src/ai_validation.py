"""
Validazione risultati AI con Pydantic
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class MovementResult(BaseModel):
    """Modello Pydantic per validare risultato rilevamento movimento da AI"""
    is_movement: bool = Field(..., description="Indica se è un movimento")
    type: Optional[str] = Field(None, description="Tipo movimento: 'consumo' o 'rifornimento'")
    quantity: Optional[int] = Field(None, description="Quantità (deve essere > 0)")
    wine_name: Optional[str] = Field(None, description="Nome vino")
    
    @validator('type')
    def validate_type(cls, v):
        """Valida che type sia 'consumo' o 'rifornimento'"""
        if v and v.lower() not in ['consumo', 'rifornimento', 'consumption', 'replenishment']:
            logger.warning(f"[AI_VALIDATION] Tipo movimento non valido: {v}")
            return None
        # Normalizza a italiano
        if v:
            v_lower = v.lower()
            if v_lower in ['consumption', 'consumo']:
                return 'consumo'
            elif v_lower in ['replenishment', 'rifornimento']:
                return 'rifornimento'
        return v
    
    @validator('quantity')
    def validate_quantity(cls, v):
        """Valida che quantity sia > 0"""
        if v is None:
            return None
        try:
            qty = int(v)
            if qty <= 0:
                logger.warning(f"[AI_VALIDATION] Quantità non valida (<= 0): {qty}")
                return None
            return qty
        except (ValueError, TypeError):
            logger.warning(f"[AI_VALIDATION] Quantità non convertibile a int: {v}")
            return None
    
    @validator('wine_name')
    def validate_wine_name(cls, v):
        """Valida che wine_name non sia vuoto"""
        if v and isinstance(v, str) and v.strip():
            return v.strip()
        return None


def validate_movement_result(result: dict) -> Optional[MovementResult]:
    """
    Valida risultato rilevamento movimento da AI usando Pydantic.
    
    Args:
        result: Dict con chiavi is_movement, type, quantity, wine_name
        
    Returns:
        MovementResult validato o None se validazione fallisce
    """
    try:
        validated = MovementResult(**result)
        return validated
    except Exception as e:
        logger.error(f"[AI_VALIDATION] Errore validazione risultato movimento: {e}, result: {result}")
        return None

