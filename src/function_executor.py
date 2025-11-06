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
        from .response_templates import format_inventory_list, format_wine_not_found, format_search_no_results
        
        search_term = params.get("search_term", "").strip()
        filters = params.get("filters", {})
        limit = params.get("limit", 10)
        
        # ✅ Se ci sono filtri, normalizza valori e usa search_wines_filtered
        if filters:
            # ✅ NORMALIZZAZIONE FILTRI: Corregge typo e sinonimi
            filters = self._normalize_filters(filters)
            logger.info(f"[FUNCTION_EXECUTOR] Cercando vini con filtri (normalizzati): {filters}")
            wines = await async_db_manager.search_wines_filtered(self.telegram_id, filters, limit=limit)
            
            if not wines:
                return {
                    "success": True,
                    "formatted_message": format_search_no_results(filters),
                    "use_template": True
                }
            else:
                return {
                    "success": True,
                    "formatted_message": format_inventory_list(wines, limit=limit),
                    "use_template": True
                }
        
        # ✅ Se no filtri ma c'è search_term, usa search_wines normale
        if search_term:
            wines = await async_db_manager.search_wines(self.telegram_id, search_term, limit=limit)
            
            if not wines:
                return {
                    "success": True,
                    "formatted_message": format_wine_not_found(search_term),
                    "use_template": True
                }
            elif len(wines) == 1:
                # Un solo vino - ritorna template dettagliato
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
        
        # ✅ Se né filtri né search_term, ritorna lista completa
        wines = await async_db_manager.get_user_wines(self.telegram_id)
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
    
    def _normalize_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizza valori dei filtri per correggere typo e sinonimi.
        Usa rapidfuzz per fuzzy matching su valori country, region, wine_type.
        """
        normalized = filters.copy()
        
        # Mappa sinonimi comuni per country
        country_synonyms = {
            'stati uniti': 'USA', 'stati uniti d\'america': 'USA', 'america': 'USA', 'united states': 'USA', 'us': 'USA',
            'italia': 'Italia', 'italiano': 'Italia', 'italiani': 'Italia', 'italiane': 'Italia', 'italy': 'Italia',
            'francia': 'Francia', 'francese': 'Francia', 'francesi': 'Francia', 'france': 'Francia',
            'spagna': 'Spagna', 'spagnolo': 'Spagna', 'spagnoli': 'Spagna', 'spain': 'Spagna',
            'germania': 'Germania', 'tedesco': 'Germania', 'tedeschi': 'Germania', 'germany': 'Germania',
            'portogallo': 'Portogallo', 'portoghese': 'Portogallo', 'portoghesi': 'Portogallo', 'portugal': 'Portogallo',
            'australia': 'Australia', 'australiano': 'Australia', 'australiani': 'Australia',
            'cile': 'Cile', 'cileno': 'Cile', 'cileni': 'Cile', 'chile': 'Cile',
            'argentina': 'Argentina', 'argentino': 'Argentina', 'argentini': 'Argentina',
        }
        
        # Mappa sinonimi comuni per wine_type
        wine_type_synonyms = {
            'rosso': 'rosso', 'rossi': 'rosso', 'red': 'rosso',
            'bianco': 'bianco', 'bianchi': 'bianco', 'bianche': 'bianco', 'white': 'bianco',
            'spumante': 'spumante', 'spumanti': 'spumante', 'sparkling': 'spumante', 'champagne': 'spumante',
            'rosato': 'rosato', 'rosati': 'rosato', 'rosé': 'rosato', 'rose': 'rosato',
        }
        
        # Normalizza country
        if 'country' in normalized and normalized['country']:
            country_lower = str(normalized['country']).lower().strip()
            if country_lower in country_synonyms:
                normalized['country'] = country_synonyms[country_lower]
                logger.info(f"[FUNCTION_EXECUTOR] Normalizzato country: '{country_lower}' → '{normalized['country']}'")
            else:
                # Prova fuzzy matching con rapidfuzz
                try:
                    from rapidfuzz import fuzz, process
                    valid_countries = ['USA', 'Italia', 'Francia', 'Spagna', 'Germania', 'Portogallo', 'Australia', 'Cile', 'Argentina']
                    best_match = process.extractOne(
                        country_lower,
                        valid_countries,
                        scorer=fuzz.WRatio,
                        score_cutoff=70
                    )
                    if best_match:
                        matched_country, score, _ = best_match
                        logger.info(
                            f"[FUNCTION_EXECUTOR] Fuzzy matching country: '{country_lower}' → '{matched_country}' "
                            f"(similarità: {score:.1f}%)"
                        )
                        normalized['country'] = matched_country
                except ImportError:
                    pass
                except Exception as e:
                    logger.error(f"[FUNCTION_EXECUTOR] Errore fuzzy matching country: {e}")
        
        # Normalizza wine_type
        if 'wine_type' in normalized and normalized['wine_type']:
            wine_type_lower = str(normalized['wine_type']).lower().strip()
            if wine_type_lower in wine_type_synonyms:
                normalized['wine_type'] = wine_type_synonyms[wine_type_lower]
                logger.info(f"[FUNCTION_EXECUTOR] Normalizzato wine_type: '{wine_type_lower}' → '{normalized['wine_type']}'")
            else:
                # Prova fuzzy matching con rapidfuzz
                try:
                    from rapidfuzz import fuzz, process
                    valid_types = ['rosso', 'bianco', 'spumante', 'rosato']
                    best_match = process.extractOne(
                        wine_type_lower,
                        valid_types,
                        scorer=fuzz.WRatio,
                        score_cutoff=70
                    )
                    if best_match:
                        matched_type, score, _ = best_match
                        logger.info(
                            f"[FUNCTION_EXECUTOR] Fuzzy matching wine_type: '{wine_type_lower}' → '{matched_type}' "
                            f"(similarità: {score:.1f}%)"
                        )
                        normalized['wine_type'] = matched_type
                except ImportError:
                    pass
                except Exception as e:
                    logger.error(f"[FUNCTION_EXECUTOR] Errore fuzzy matching wine_type: {e}")
        
        # Normalizza region (usa rapidfuzz per typo)
        if 'region' in normalized and normalized['region']:
            region_value = str(normalized['region']).strip()
            # Prova fuzzy matching con rapidfuzz su regioni comuni
            try:
                from rapidfuzz import fuzz, process
                common_regions = [
                    'Toscana', 'Piemonte', 'Veneto', 'Sicilia', 'Sardegna', 'Lombardia', 'Marche', 'Umbria', 'Lazio',
                    'Puglia', 'Abruzzo', 'Friuli', 'Trentino', 'Alto Adige', 'Campania', 'Liguria', 'Emilia', 'Romagna'
                ]
                best_match = process.extractOne(
                    region_value,
                    common_regions,
                    scorer=fuzz.WRatio,
                    score_cutoff=70
                )
                if best_match:
                    matched_region, score, _ = best_match
                    if score >= 70:
                        logger.info(
                            f"[FUNCTION_EXECUTOR] Fuzzy matching region: '{region_value}' → '{matched_region}' "
                            f"(similarità: {score:.1f}%)"
                        )
                        normalized['region'] = matched_region
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"[FUNCTION_EXECUTOR] Errore fuzzy matching region: {e}")
        
        return normalized
    
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
        """Info vino per query - USA TEMPLATE con fuzzy matching per typo"""
        from .database_async import async_db_manager
        from .response_templates import format_wine_info, format_wine_not_found
        
        wine_query = params.get("wine_query", "").strip()
        if not wine_query:
            return {"success": False, "error": "wine_query non fornito"}
        
        # ✅ FUZZY MATCHING: Cerca vini simili per correggere typo
        wines = await async_db_manager.search_wines(self.telegram_id, wine_query, limit=10)
        
        if not wines:
            # Se non trova match, prova ricerca più permissiva (primi caratteri)
            if len(wine_query) >= 4:
                short_search = wine_query[:4].lower()
                wines = await async_db_manager.search_wines(self.telegram_id, short_search, limit=10)
        
        # Se ancora non trova, usa rapidfuzz per fuzzy matching su tutti i vini
        if not wines:
            try:
                from rapidfuzz import fuzz, process
                all_wines = await async_db_manager.get_user_wines(self.telegram_id)
                
                if all_wines:
                    # Cerca il vino più simile usando rapidfuzz
                    wine_names = [w.name for w in all_wines]
                    best_match = process.extractOne(
                        wine_query,
                        wine_names,
                        scorer=fuzz.WRatio,  # Weighted Ratio (migliore per typo)
                        score_cutoff=70  # Minimo 70% di similarità
                    )
                    
                    if best_match:
                        matched_name, score, _ = best_match
                        logger.info(
                            f"[FUNCTION_EXECUTOR] Fuzzy matching rapidfuzz per info vino: '{wine_query}' → '{matched_name}' "
                            f"(similarità: {score:.1f}%)"
                        )
                        # Trova il vino corrispondente
                        wines = [w for w in all_wines if w.name == matched_name]
            except ImportError:
                logger.warning("[FUNCTION_EXECUTOR] rapidfuzz non disponibile, salto fuzzy matching avanzato")
            except Exception as e:
                logger.error(f"[FUNCTION_EXECUTOR] Errore fuzzy matching rapidfuzz: {e}")
        
        if not wines:
            return {
                "success": True,
                "formatted_message": format_wine_not_found(wine_query),
                "use_template": True
            }
        
        # Se trova più vini, usa il primo (più probabile)
        selected_wine = wines[0]
        if len(wines) > 1:
            logger.info(
                f"[FUNCTION_EXECUTOR] Trovati {len(wines)} vini per '{wine_query}', uso il primo: '{selected_wine.name}'"
            )
        
        return {
            "success": True,
            "formatted_message": format_wine_info(selected_wine),
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

