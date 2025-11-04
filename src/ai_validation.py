"""
Validazione output LLM con Pydantic per prevenire mutazioni stato errate.
"""
import logging
from pydantic import BaseModel, validator
from typing import Optional

logger = logging.getLogger(__name__)


class MovementDetectionResult(BaseModel):
    """Schema validazione movimento rilevato da AI"""
    is_movement: bool
    type: Optional[str] = None  # 'consumo' o 'rifornimento'
    quantity: Optional[int] = None
    wine_name: Optional[str] = None
    
    @validator('type')
    def validate_type(cls, v):
        if v and v not in ['consumo', 'rifornimento']:
            raise ValueError(f"type must be 'consumo' or 'rifornimento', got {v}")
        return v
    
    @validator('quantity')
    def validate_quantity(cls, v):
        if v is not None and (v <= 0 or v > 10000):
            raise ValueError(f"quantity must be 1-10000, got {v}")
        return v


def validate_movement_result(json_data: dict) -> Optional[MovementDetectionResult]:
    """Valida risultato movimento da AI"""
    try:
        return MovementDetectionResult(**json_data)
    except Exception as e:
        logger.error(f"Invalid movement result from AI: {e}, data: {json_data}")
        return None





