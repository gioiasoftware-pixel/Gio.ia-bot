"""
Client per comunicazione con il microservizio processor
"""
import aiohttp
import logging
from typing import Dict, Any, Optional
from .config import PROCESSOR_URL

logger = logging.getLogger(__name__)

class ProcessorClient:
    """Client per comunicazione con il processor"""
    
    def __init__(self):
        self.base_url = PROCESSOR_URL
        self.timeout = aiohttp.ClientTimeout(total=30)
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica stato del processor"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        # Controlla content-type
                        content_type = response.headers.get('content-type', '')
                        if 'application/json' in content_type:
                            return await response.json()
                        else:
                            # Se non è JSON, leggi come testo e prova a parsare
                            text_response = await response.text()
                            logger.warning(f"Processor returned text instead of JSON: {text_response[:100]}")
                            return {
                                "status": "healthy",
                                "service": "gioia-processor",
                                "message": "Processor responding but not JSON format",
                                "raw_response": text_response[:200]
                            }
                    else:
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}",
                            "service": "gioia-processor"
                        }
        except Exception as e:
            logger.error(f"Error checking processor health: {e}")
            return {
                "status": "error",
                "error": str(e),
                "service": "gioia-processor"
            }
    
    async def process_inventory(self, telegram_id: int, business_name: str, 
                               file_type: str, file_content: bytes, 
                               file_name: str = "inventario") -> Dict[str, Any]:
        """Invia file inventario al processor per elaborazione"""
        try:
            import json
            
            # Determina content-type basato sul tipo di file
            if file_type == 'csv':
                mime_type = 'text/csv'
            elif file_type in ['excel', 'xlsx', 'xls']:
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif file_type == 'photo':
                mime_type = 'image/jpeg'
            else:
                mime_type = 'application/octet-stream'
            
            # Crea FormData con ordine corretto per FastAPI standard
            data = aiohttp.FormData()
            
            # Aggiungi campi di testo PRIMA (ordine corretto per FastAPI)
            data.add_field('telegram_id', str(telegram_id))
            data.add_field('business_name', business_name)
            data.add_field('file_type', file_type)
            
            # Aggiungi file PER ULTIMO
            data.add_field('file', file_content, filename=file_name, content_type=mime_type)
            
            logger.info(f"Sending inventory to processor: {telegram_id}, {business_name}, {file_type}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                
                async with session.post(f"{self.base_url}/process-inventory", data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Inventory processed successfully: {result.get('total_wines', 0)} wines")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Processor error: {response.status} - {error_text}")
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text}",
                            "telegram_id": telegram_id
                        }
        except Exception as e:
            logger.error(f"Error processing inventory: {e}")
            return {
                "status": "error",
                "error": str(e),
                "telegram_id": telegram_id
            }
    
    async def get_status(self, telegram_id: int) -> Dict[str, Any]:
        """Ottieni stato elaborazione per utente"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/status/{telegram_id}") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}",
                            "telegram_id": telegram_id
                        }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "telegram_id": telegram_id
            }
    
    async def test_ai(self, text: str) -> Dict[str, Any]:
        """Test AI processing con testo"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                data = aiohttp.FormData()
                data.add_field('text', text)
                
                async with session.post(f"{self.base_url}/ai/test", data=data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text}"
                        }
        except Exception as e:
            logger.error(f"Error testing AI: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

# Istanza globale del client
processor_client = ProcessorClient()

