"""
Client per comunicazione con il microservizio processor
"""
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional
from .config import PROCESSOR_URL

logger = logging.getLogger(__name__)

class ProcessorClient:
    """Client per comunicazione con il processor"""
    
    def __init__(self):
        self.base_url = PROCESSOR_URL
        self.timeout = aiohttp.ClientTimeout(total=120)  # 2 minuti per elaborazione file
    
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
                               file_name: str = "inventario", file_id: str = None) -> Dict[str, Any]:
        """
        Invia file al processor e ritorna job_id.
        L'elaborazione avviene in background - usa get_job_status per verificare progresso.
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                # Prepara form data multipart
                form = aiohttp.FormData()
                form.add_field('telegram_id', str(telegram_id))
                form.add_field('business_name', business_name)
                form.add_field('file_type', file_type)
                # Invia file come campo 'file' (nome richiesto dall'endpoint FastAPI)
                form.add_field('file', file_content, filename=file_name, content_type='application/octet-stream')
                
                logger.info(f"Sending inventory to processor: {telegram_id}, {business_name}, {file_type}, size={len(file_content)} bytes")
                
                async with session.post(
                    f"{self.base_url}/process-inventory",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30)  # Timeout corto, ritorna subito job_id
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        job_id = result.get('job_id')
                        logger.info(f"Job created: {job_id}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Processor error HTTP {response.status}: {error_text}")
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text[:200]}",
                            "telegram_id": telegram_id
                        }
        except asyncio.TimeoutError:
            logger.error(f"Timeout creating job")
            return {
                "status": "error",
                "error": "Timeout creando job. Riprova più tardi.",
                "telegram_id": telegram_id
            }
        except Exception as e:
            logger.error(f"Error sending inventory to processor: {e}")
            return {
                "status": "error",
                "error": str(e),
                "telegram_id": telegram_id
            }
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Ottieni stato elaborazione per job_id
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{self.base_url}/status/{job_id}") as response:
                    if response.status == 200:
                        try:
                            return await response.json()
                        except Exception as json_error:
                            error_text = await response.text()
                            logger.error(f"Error parsing JSON response for job {job_id}: {json_error}, response: {error_text[:500]}")
                            return {
                                "status": "error",
                                "error": f"Invalid JSON response: {str(json_error)}"
                            }
                    elif response.status == 404:
                        return {
                            "status": "error",
                            "error": f"Job {job_id} not found"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Error getting job status HTTP {response.status} for job {job_id}: {error_text[:500]}")
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout getting job status for {job_id}: {e}")
            return {
                "status": "error",
                "error": f"Timeout connecting to processor (job {job_id})"
            }
        except aiohttp.ClientError as e:
            logger.error(f"Client error getting job status for {job_id}: {e}")
            return {
                "status": "error",
                "error": f"Connection error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {type(e).__name__}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}"
            }
    
    async def wait_for_job_completion(self, job_id: str, max_wait_seconds: int = 3600, 
                                      poll_interval: int = 10) -> Dict[str, Any]:
        """
        Attende completamento job con polling.
        Ritorna risultato quando job è completato o errore.
        """
        import time
        start_time = time.time()
        
        logger.info(f"Waiting for job {job_id} to complete (max {max_wait_seconds}s, poll every {poll_interval}s)")
        
        while True:
            # Controlla timeout
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                logger.error(f"Job {job_id} timeout after {max_wait_seconds} seconds")
                return {
                    "status": "error",
                    "error": f"Job timeout dopo {max_wait_seconds} secondi",
                    "job_id": job_id
                }
            
            # Poll status
            try:
                status = await self.get_job_status(job_id)
            except Exception as e:
                logger.error(f"Exception calling get_job_status for {job_id}: {e}", exc_info=True)
                return {
                    "status": "error",
                    "error": f"Error polling job status: {str(e)}",
                    "job_id": job_id
                }
            
            # Verifica che status sia un dict valido
            if not isinstance(status, dict):
                logger.error(f"Invalid status response for job {job_id}: {type(status)} = {status}")
                return {
                    "status": "error",
                    "error": "Invalid response format from processor",
                    "job_id": job_id
                }
            
            job_status = status.get("status")
            
            if job_status == "completed":
                # Job completato - ritorna risultato
                result = status.get("result", {})
                if not isinstance(result, dict):
                    logger.error(f"Invalid result format for job {job_id}: {type(result)} = {result}")
                    # Prova a costruire risultato dai campi diretti di status
                    result = {
                        "status": "success",
                        "saved_wines": status.get("saved_wines", 0),
                        "total_wines": status.get("total_wines", 0),
                        "warning_count": status.get("warning_count", 0),
                        "error_count": status.get("error_count", 0)
                    }
                
                logger.info(f"Job {job_id} completed: {result.get('saved_wines', 0)} wines saved")
                return result
            elif job_status == "error":
                # Job errore
                error_msg = status.get("error", "Unknown error")
                logger.error(f"Job {job_id} error: {error_msg}")
                return {
                    "status": "error",
                    "error": error_msg,
                    "job_id": job_id
                }
            elif job_status in ["pending", "processing"]:
                # Ancora in elaborazione - mostra progress
                progress = status.get("progress_percent", 0)
                processed = status.get("processed_wines", 0)
                total = status.get("total_wines", 0)
                logger.info(f"Job {job_id} progress: {progress}% ({processed}/{total} wines)")
                await asyncio.sleep(poll_interval)
            else:
                # Stato sconosciuto - log dettagliato e continua polling
                logger.warning(f"Job {job_id} unknown status: {job_status}, full response: {status}")
                await asyncio.sleep(poll_interval)
    
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
    
    async def create_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """
        Crea le 4 tabelle per un utente quando viene dato il nome del locale.
        Chiamato durante l'onboarding.
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                form = aiohttp.FormData()
                form.add_field('telegram_id', str(telegram_id))
                form.add_field('business_name', business_name)
                
                async with session.post(f"{self.base_url}/create-tables", data=form) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Tables created for {telegram_id}/{business_name}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Error creating tables HTTP {response.status}: {error_text}")
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def delete_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """
        Cancella tabelle database per utente.
        SOLO PER telegram_id = 927230913 (admin)
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                url = f"{self.base_url}/tables/{telegram_id}"
                params = {"business_name": business_name}
                
                async with session.delete(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "message": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"Error deleting tables: {e}")
            return {
                "success": False,
                "message": str(e)
            }
    
    async def process_movement(self, telegram_id: int, business_name: str, 
                               wine_name: str, movement_type: str, 
                               quantity: int, notes: str = None) -> Dict[str, Any]:
        """
        Processa movimento inventario (consumo o rifornimento).
        Aggiorna quantità vino e salva log nel processor.
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                form = aiohttp.FormData()
                form.add_field('telegram_id', str(telegram_id))
                form.add_field('business_name', business_name)
                form.add_field('wine_name', wine_name)
                form.add_field('movement_type', movement_type)  # 'consumo' o 'rifornimento'
                form.add_field('quantity', str(quantity))
                if notes:
                    form.add_field('notes', notes)
                
                async with session.post(f"{self.base_url}/inventory-movement", data=form) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Movement processed: {telegram_id}/{business_name} - {movement_type} {quantity} {wine_name}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Error processing movement HTTP {response.status}: {error_text}")
                        try:
                            error_json = await response.json()
                            return {
                                "status": "error",
                                "error": error_json.get("detail", error_text[:200])
                            }
                        except:
                            return {
                                "status": "error",
                                "error": f"HTTP {response.status}: {error_text[:200]}"
                            }
        except Exception as e:
            logger.error(f"Error processing movement: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

# Istanza globale del client
processor_client = ProcessorClient()

