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
        
        # ✅ Gestione movimenti multipli
        if intent.type == "multiple_movements":
            return await self._execute_multiple_movements(intent.parameters.get("movements", []))
        
        # Importa FunctionExecutor
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
    
    async def _execute_multiple_movements(self, movements: list) -> Dict[str, Any]:
        """Esegue movimenti multipli in sequenza"""
        from .function_executor import FunctionExecutor
        from .response_templates import format_movement_confirmation
        
        executor = FunctionExecutor(self.telegram_id, self.context)
        results = []
        errors = []
        
        for i, movement in enumerate(movements, 1):
            movement_type = movement.get("type")
            wine_name = movement.get("wine_name")
            quantity = movement.get("quantity")
            
            logger.info(
                f"[INTENT_HANDLER] Eseguendo movimento {i}/{len(movements)}: "
                f"{movement_type} {quantity} {wine_name}"
            )
            
            handler = "register_consumption" if movement_type == "consumption" else "register_replenishment"
            result = await executor.execute_function(handler, {
                "wine_name": wine_name,
                "quantity": quantity
            })
            
            if result.get("success"):
                results.append({
                    "movement_type": movement_type,
                    "wine_name": wine_name,
                    "quantity": quantity,
                    "result": result
                })
            else:
                errors.append({
                    "movement_type": movement_type,
                    "wine_name": wine_name,
                    "quantity": quantity,
                    "error": result.get("error", "Errore sconosciuto")
                })
        
        # Formatta risposta combinata
        if errors:
            # Se ci sono errori, mostra tutti i risultati
            lines = ["📋 **Riepilogo Movimenti**", "━" * 30]
            for r in results:
                lines.append(
                    f"✅ {r['movement_type'].capitalize()}: {r['quantity']} {r['wine_name']}"
                )
            for e in errors:
                lines.append(
                    f"❌ {e['movement_type'].capitalize()}: {e['quantity']} {e['wine_name']} - {e['error']}"
                )
            lines.append("━" * 30)
            return {
                "success": len(errors) < len(movements),  # Success se almeno uno è riuscito
                "formatted_message": "\n".join(lines),
                "used_template": True
            }
        else:
            # Tutti riusciti
            lines = ["✅ **Movimenti registrati**", "━" * 30]
            for r in results:
                result_data = r["result"].get("formatted_message", "")
                # Estrai info dal template se disponibile
                lines.append(f"✅ {r['movement_type'].capitalize()}: {r['quantity']} {r['wine_name']}")
            lines.append("━" * 30)
            lines.append(f"💾 **{len(results)} movimenti salvati** nel sistema")
            return {
                "success": True,
                "formatted_message": "\n".join(lines),
                "used_template": True
            }

