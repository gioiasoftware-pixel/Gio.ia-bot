"""
Intent Handler - Esegue azione basata su intento classificato
"""
import logging
from typing import Dict, Any
from telegram.ext import ContextTypes
from .intent_classifier import Intent

logger = logging.getLogger(__name__)


class IntentHandler:
    """Esegue azione basata su intento classificato"""
    
    def __init__(self, telegram_id: int, context: ContextTypes.DEFAULT_TYPE):
        self.telegram_id = telegram_id
        self.context = context
    
    async def execute_intent(self, intent: Intent) -> Dict[str, Any]:
        """Esegue azione basata su intento"""
        if intent.type == "unknown" or not intent.handler:
            logger.warning(f"[INTENT_HANDLER] Intent unknown o handler non disponibile: {intent.type}")
            return {
                "success": False,
                "error": "Intent unknown o handler non disponibile"
            }
        
        logger.info(
            f"[INTENT_HANDLER] Eseguendo intent: {intent.type} "
            f"(handler={intent.handler}, confidence={intent.confidence:.2f})"
        )
        
        # Importa FunctionExecutor (sarà creato nella Fase 2)
        try:
            from .function_executor import FunctionExecutor
            
            executor = FunctionExecutor(self.telegram_id, self.context)
            result = await executor.execute_function(intent.handler, intent.parameters)
            
            # Se ha template, usalo
            if result.get("use_template") and result.get("formatted_message"):
                logger.info(f"[INTENT_HANDLER] Risposta formattata con template")
                return {
                    "success": True,
                    "formatted_message": result["formatted_message"],
                    "used_template": True
                }
            
            # Altrimenti ritorna risultato grezzo
            return result
            
        except ImportError:
            # FunctionExecutor non ancora creato, ritorna errore
            logger.error(f"[INTENT_HANDLER] FunctionExecutor non disponibile (ancora da creare)")
            return {
                "success": False,
                "error": "FunctionExecutor non ancora implementato"
            }
        except Exception as e:
            logger.error(f"[INTENT_HANDLER] Errore esecuzione intent: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

