"""
Function Registry - Registra funzioni disponibili all'IA
Schema JSON per OpenAI Function Calling
"""
from typing import List, Dict


class FunctionRegistry:
    """Registra tutte le funzioni disponibili all'IA"""
    
    def get_functions(self) -> List[Dict]:
        """Ritorna schema JSON per OpenAI Function Calling"""
        return [
            {
                "name": "search_wines",
                "description": "Cerca vini nell'inventario per nome, produttore, regione, tipo, etc. Restituisce lista vini che corrispondono al termine di ricerca.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_term": {
                            "type": "string",
                            "description": "Termine di ricerca (nome vino, produttore, regione, tipo, etc.)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Numero massimo risultati da restituire",
                            "default": 10
                        }
                    },
                    "required": ["search_term"]
                }
            },
            {
                "name": "register_consumption",
                "description": "Registra un consumo (vendita/consumo) di bottiglie. Diminuisce la quantità disponibile del vino specificato.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_name": {
                            "type": "string",
                            "description": "Nome del vino da consumare"
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Numero di bottiglie consumate (deve essere positivo)"
                        }
                    },
                    "required": ["wine_name", "quantity"]
                }
            },
            {
                "name": "register_replenishment",
                "description": "Registra un rifornimento (acquisto/aggiunta) di bottiglie. Aumenta la quantità disponibile del vino specificato.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_name": {
                            "type": "string",
                            "description": "Nome del vino da rifornire"
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Numero di bottiglie aggiunte (deve essere positivo)"
                        }
                    },
                    "required": ["wine_name", "quantity"]
                }
            },
            {
                "name": "get_inventory_list",
                "description": "Ottiene lista completa inventario con filtri opzionali. Restituisce tutti i vini o filtrati per regione, tipo, paese.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "Filtra per regione (es. 'Toscana', 'Piemonte')"
                        },
                        "type": {
                            "type": "string",
                            "description": "Filtra per tipo di vino (es. 'rosso', 'bianco', 'rosato')"
                        },
                        "country": {
                            "type": "string",
                            "description": "Filtra per paese (es. 'Italia', 'Francia')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Numero massimo risultati da restituire",
                            "default": 50
                        }
                    }
                }
            },
            {
                "name": "get_inventory_statistics",
                "description": "Ottiene statistiche inventario: totale vini, totale bottiglie, valore totale, prezzo medio. Utile per avere una visione d'insieme dell'inventario.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_movement_summary",
                "description": "Ottiene riepilogo movimenti (consumi e rifornimenti) per un periodo specifico. Mostra totale movimenti, quantità consumate/aggiunte.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "enum": ["today", "week", "month", "year"],
                            "description": "Periodo per il riepilogo: 'today' (oggi), 'week' (ultima settimana), 'month' (ultimo mese), 'year' (ultimo anno)"
                        }
                    },
                    "required": ["period"]
                }
            },
            {
                "name": "get_low_stock_wines",
                "description": "Ottiene lista vini con scorte basse (quantità inferiore alla soglia). Utile per identificare vini da rifornire.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "threshold": {
                            "type": "integer",
                            "description": "Soglia minima quantità (vini con quantità < threshold vengono segnalati)",
                            "default": 5
                        }
                    }
                }
            },
            {
                "name": "update_wine_field",
                "description": "Aggiorna un campo di un vino specifico (prezzo, quantità, note, descrizione). Utile per correggere o aggiornare informazioni.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_id": {
                            "type": "integer",
                            "description": "ID del vino da aggiornare"
                        },
                        "field": {
                            "type": "string",
                            "enum": ["price", "quantity", "notes", "description"],
                            "description": "Campo da aggiornare: 'price' (prezzo), 'quantity' (quantità), 'notes' (note), 'description' (descrizione)"
                        },
                        "value": {
                            "type": "string",
                            "description": "Nuovo valore per il campo (per prezzo e quantità, usa formato numerico)"
                        }
                    },
                    "required": ["wine_id", "field", "value"]
                }
            },
            {
                "name": "get_wine_details",
                "description": "Ottiene dettagli completi di un vino specifico: nome, produttore, annata, quantità, prezzo, regione, tipo, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_id": {
                            "type": "integer",
                            "description": "ID del vino di cui ottenere i dettagli"
                        }
                    },
                    "required": ["wine_id"]
                }
            },
            {
                "name": "get_wine_info",
                "description": "Ottiene informazioni base di un vino cercandolo per nome. Restituisce dettagli se trovato, altrimenti messaggio di errore.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_query": {
                            "type": "string",
                            "description": "Nome o termine di ricerca per il vino"
                        }
                    },
                    "required": ["wine_query"]
                }
            },
            {
                "name": "get_wine_price",
                "description": "Ottiene il prezzo di un vino cercandolo per nome. Restituisce prezzo se trovato, altrimenti messaggio di errore.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_query": {
                            "type": "string",
                            "description": "Nome o termine di ricerca per il vino"
                        }
                    },
                    "required": ["wine_query"]
                }
            },
            {
                "name": "get_wine_quantity",
                "description": "Ottiene la quantità disponibile di un vino cercandolo per nome. Restituisce quantità se trovato, altrimenti messaggio di errore.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wine_query": {
                            "type": "string",
                            "description": "Nome o termine di ricerca per il vino"
                        }
                    },
                    "required": ["wine_query"]
                }
            },
            {
                "name": "get_inventory_stats",
                "description": "Ottiene statistiche rapide inventario: totale vini, totale bottiglie, vini con scorte basse. Versione semplificata di get_inventory_statistics.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

