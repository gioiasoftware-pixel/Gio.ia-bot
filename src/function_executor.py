"""
Function Executor - Esegue funzioni richieste dall'IA o dall'Intent Handler
Wrapper centralizzato per tutte le funzioni disponibili
"""
import logging
from typing import Dict, Any, Optional
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class FunctionExecutor:
    """Esegue funzioni richieste dall'IA o dall'Intent Handler"""
    
    def __init__(self, telegram_id: int, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
        self.telegram_id = telegram_id
        self.context = context
    
    async def execute_function(self, function_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Esegue funzione richiesta"""
        logger.info(f"[FUNCTION_EXECUTOR] Eseguendo: {function_name} con {parameters}")
        
        try:
            if function_name == "search_wines":
                return await self._execute_search_wines(parameters)
            elif function_name == "register_consumption":
                return await self._execute_register_consumption(parameters)
            elif function_name == "register_replenishment":
                return await self._execute_register_replenishment(parameters)
            elif function_name == "get_inventory_list":
                return await self._execute_get_inventory_list(parameters)
            elif function_name == "get_inventory_statistics":
                return await self._execute_get_inventory_statistics(parameters)
            elif function_name == "get_inventory_stats":
                return await self._execute_get_inventory_stats(parameters)
            elif function_name == "get_movement_summary":
                return await self._execute_get_movement_summary(parameters)
            elif function_name == "get_low_stock_wines":
                return await self._execute_get_low_stock_wines(parameters)
            elif function_name == "update_wine_field":
                return await self._execute_update_wine_field(parameters)
            elif function_name == "get_wine_details":
                return await self._execute_get_wine_details(parameters)
            elif function_name == "get_wine_info":
                return await self._execute_get_wine_info(parameters)
            elif function_name == "get_wine_price":
                return await self._execute_get_wine_price(parameters)
            elif function_name == "get_wine_quantity":
                return await self._execute_get_wine_quantity(parameters)
            else:
                logger.warning(f"[FUNCTION_EXECUTOR] Funzione '{function_name}' non riconosciuta")
                return {"success": False, "error": f"Funzione '{function_name}' non riconosciuta"}
        except Exception as e:
            logger.error(f"[FUNCTION_EXECUTOR] Errore esecuzione {function_name}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _execute_search_wines(self, params: Dict) -> Dict:
        """Cerca vini - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_inventory_list, format_wine_not_found
        
        search_term = params.get("search_term", "").strip()
        limit = params.get("limit", 10)
        
        if not search_term:
            # Se search_term vuoto, ritorna lista completa
            wines = await async_db_manager.get_user_wines(self.telegram_id)
        else:
            wines = await async_db_manager.search_wines(self.telegram_id, search_term, limit=limit)
        
        if not wines:
            return {
                "success": True,
                "formatted_message": format_wine_not_found(search_term if search_term else "nessun termine"),
                "use_template": True
            }
        elif len(wines) == 1:
            # Un solo vino - ritorna dati grezzi per AI o template dettagliato
            from .response_templates import format_wine_info
            return {
                "success": True,
                "formatted_message": format_wine_info(wines[0]),
                "use_template": True,
                "count": 1,
                "wines": [{"id": w.id, "name": w.name, "producer": w.producer, "quantity": w.quantity} for w in wines]
            }
        else:
            return {
                "success": True,
                "formatted_message": format_inventory_list(wines, limit=limit),
                "use_template": True
            }
    
    async def _execute_register_consumption(self, params: Dict) -> Dict:
        """Registra consumo - USA TEMPLATE"""
        from .processor_client import ProcessorClient
        from .database_async import async_db_manager
        from .response_templates import format_movement_confirmation
        
        wine_name = params.get("wine_name", "").strip()
        quantity = params.get("quantity", 0)
        
        if not wine_name or quantity <= 0:
            return {"success": False, "error": "Nome vino o quantità non validi"}
        
        user = await async_db_manager.get_user_by_telegram_id(self.telegram_id)
        if not user or not user.business_name:
            return {"success": False, "error": "Business name non trovato. Completa l'onboarding con /start"}
        
        processor_client = ProcessorClient()
        result = await processor_client.process_movement(
            telegram_id=self.telegram_id,
            business_name=user.business_name,
            wine_name=wine_name,
            movement_type="consumo",
            quantity=quantity
        )
        
        if result.get("status") == "success":
            return {
                "success": True,
                "formatted_message": format_movement_confirmation(
                    wine_name=result.get("wine_name", wine_name),
                    movement_type="consumo",
                    quantity=quantity,
                    quantity_before=result.get("quantity_before", 0),
                    quantity_after=result.get("quantity_after", 0)
                ),
                "use_template": True
            }
        else:
            error_msg = result.get("error", result.get("error_message", "Errore sconosciuto"))
            return {"success": False, "error": error_msg}
    
    async def _execute_register_replenishment(self, params: Dict) -> Dict:
        """Registra rifornimento - USA TEMPLATE"""
        from .processor_client import ProcessorClient
        from .database_async import async_db_manager
        from .response_templates import format_movement_confirmation
        
        wine_name = params.get("wine_name", "").strip()
        quantity = params.get("quantity", 0)
        
        if not wine_name or quantity <= 0:
            return {"success": False, "error": "Nome vino o quantità non validi"}
        
        user = await async_db_manager.get_user_by_telegram_id(self.telegram_id)
        if not user or not user.business_name:
            return {"success": False, "error": "Business name non trovato. Completa l'onboarding con /start"}
        
        processor_client = ProcessorClient()
        result = await processor_client.process_movement(
            telegram_id=self.telegram_id,
            business_name=user.business_name,
            wine_name=wine_name,
            movement_type="rifornimento",
            quantity=quantity
        )
        
        if result.get("status") == "success":
            return {
                "success": True,
                "formatted_message": format_movement_confirmation(
                    wine_name=result.get("wine_name", wine_name),
                    movement_type="rifornimento",
                    quantity=quantity,
                    quantity_before=result.get("quantity_before", 0),
                    quantity_after=result.get("quantity_after", 0)
                ),
                "use_template": True
            }
        else:
            error_msg = result.get("error", result.get("error_message", "Errore sconosciuto"))
            return {"success": False, "error": error_msg}
    
    async def _execute_get_inventory_list(self, params: Dict) -> Dict:
        """Lista inventario - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_inventory_list
        
        wines = await async_db_manager.get_user_wines(self.telegram_id)
        
        # Applica filtri
        region = params.get("region", "").strip().lower() if params.get("region") else None
        wine_type = params.get("type", "").strip().lower() if params.get("type") else None
        country = params.get("country", "").strip().lower() if params.get("country") else None
        limit = params.get("limit", 50)
        
        filtered = []
        for w in wines:
            if region and (not w.region or region not in w.region.lower()):
                continue
            if wine_type and (not w.wine_type or wine_type not in w.wine_type.lower()):
                continue
            if country and (not w.country or country not in w.country.lower()):
                continue
            filtered.append(w)
        
        filtered = filtered[:limit]
        
        return {
            "success": True,
            "formatted_message": format_inventory_list(filtered, limit=limit),
            "use_template": True
        }
    
    async def _execute_get_inventory_statistics(self, params: Dict) -> Dict:
        """Statistiche inventario - CALCOLA E FORMATTA"""
        from .database_async import async_db_manager
        
        wines = await async_db_manager.get_user_wines(self.telegram_id)
        
        total_wines = len(wines)
        total_bottles = sum(w.quantity or 0 for w in wines)
        total_value = sum((w.selling_price or 0) * (w.quantity or 0) for w in wines)
        avg_price = total_value / total_bottles if total_bottles > 0 else 0
        
        # Formatta messaggio (NO template specifico, ma formattato)
        message = (
            f"📊 **Statistiche Inventario**\n"
            f"{'━' * 30}\n"
            f"🍷 **Totale vini:** {total_wines}\n"
            f"📦 **Totale bottiglie:** {total_bottles}\n"
            f"💰 **Valore totale:** €{total_value:,.2f}\n"
            f"📈 **Prezzo medio:** €{avg_price:.2f}/bottiglia\n"
            f"{'━' * 30}"
        )
        
        return {
            "success": True,
            "formatted_message": message,
            "use_template": True  # Formattato, anche se non template dedicato
        }
    
    async def _execute_get_inventory_stats(self, params: Dict) -> Dict:
        """Statistiche rapide inventario - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_inventory_summary
        
        stats = await async_db_manager.get_inventory_stats(self.telegram_id)
        
        return {
            "success": True,
            "formatted_message": format_inventory_summary(
                telegram_id=self.telegram_id,
                total_wines=stats.get('total_wines', 0),
                total_quantity=stats.get('total_bottles', 0),
                low_stock_count=stats.get('low_stock', 0)
            ),
            "use_template": True
        }
    
    async def _execute_get_movement_summary(self, params: Dict) -> Dict:
        """Riepilogo movimenti - USA TEMPLATE"""
        from .database_async import get_movement_summary
        from .response_templates import format_movement_period_summary
        
        period = params.get("period", "month")
        if period not in ["today", "week", "month", "year"]:
            period = "month"
        
        try:
            summary = await get_movement_summary(self.telegram_id, period)
            return {
                "success": True,
                "formatted_message": format_movement_period_summary(period, summary),
                "use_template": True
            }
        except Exception as e:
            logger.error(f"[FUNCTION_EXECUTOR] Errore get_movement_summary: {e}")
            return {"success": False, "error": f"Errore nel calcolo dei movimenti: {str(e)}"}
    
    async def _execute_get_low_stock_wines(self, params: Dict) -> Dict:
        """Vini con scorte basse - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_low_stock_alert
        
        threshold = params.get("threshold", 5)
        wines = await async_db_manager.get_user_wines(self.telegram_id)
        low_stock = [w for w in wines if (w.quantity or 0) < threshold]
        
        if not low_stock:
            formatted = "✅ Nessun vino con scorte basse"
        else:
            formatted = format_low_stock_alert(low_stock)
        
        return {
            "success": True,
            "formatted_message": formatted,
            "use_template": True
        }
    
    async def _execute_update_wine_field(self, params: Dict) -> Dict:
        """Aggiorna campo vino - MESSAGGIO SEMPLICE"""
        # TODO: Implementare quando processor supporta update_wine_field
        # Per ora ritorna errore
        return {
            "success": False,
            "error": "Funzione update_wine_field non ancora implementata nel processor"
        }
    
    async def _execute_get_wine_details(self, params: Dict) -> Dict:
        """Dettagli vino - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_wine_info
        
        wine_id = params.get("wine_id")
        if not wine_id:
            return {"success": False, "error": "wine_id non fornito"}
        
        wines = await async_db_manager.get_user_wines(self.telegram_id)
        wine = next((w for w in wines if w.id == wine_id), None)
        
        if not wine:
            return {"success": False, "error": f"Vino con ID {wine_id} non trovato"}
        
        return {
            "success": True,
            "formatted_message": format_wine_info(wine),
            "use_template": True
        }
    
    async def _execute_get_wine_info(self, params: Dict) -> Dict:
        """Info vino per query - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_wine_info, format_wine_not_found
        
        wine_query = params.get("wine_query", "").strip()
        if not wine_query:
            return {"success": False, "error": "wine_query non fornito"}
        
        wines = await async_db_manager.search_wines(self.telegram_id, wine_query, limit=1)
        
        if not wines:
            return {
                "success": True,
                "formatted_message": format_wine_not_found(wine_query),
                "use_template": True
            }
        
        return {
            "success": True,
            "formatted_message": format_wine_info(wines[0]),
            "use_template": True
        }
    
    async def _execute_get_wine_price(self, params: Dict) -> Dict:
        """Prezzo vino - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_wine_price, format_wine_not_found
        
        wine_query = params.get("wine_query", "").strip()
        if not wine_query:
            return {"success": False, "error": "wine_query non fornito"}
        
        wines = await async_db_manager.search_wines(self.telegram_id, wine_query, limit=1)
        
        if not wines:
            return {
                "success": True,
                "formatted_message": format_wine_not_found(wine_query),
                "use_template": True
            }
        
        return {
            "success": True,
            "formatted_message": format_wine_price(wines[0]),
            "use_template": True
        }
    
    async def _execute_get_wine_quantity(self, params: Dict) -> Dict:
        """Quantità vino - USA TEMPLATE"""
        from .database_async import async_db_manager
        from .response_templates import format_wine_quantity, format_wine_not_found
        
        wine_query = params.get("wine_query", "").strip()
        if not wine_query:
            return {"success": False, "error": "wine_query non fornito"}
        
        wines = await async_db_manager.search_wines(self.telegram_id, wine_query, limit=1)
        
        if not wines:
            return {
                "success": True,
                "formatted_message": format_wine_not_found(wine_query),
                "use_template": True
            }
        
        return {
            "success": True,
            "formatted_message": format_wine_quantity(wines[0]),
            "use_template": True
        }

