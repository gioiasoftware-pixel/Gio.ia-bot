"""
Client per comunicare con il processor microservice
"""
import logging
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from .config import PROCESSOR_URL

logger = logging.getLogger(__name__)


class ProcessorClient:
    """Client HTTP per processor microservice"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or PROCESSOR_URL
        if not self.base_url:
            self.base_url = "https://gioia-processor-production.up.railway.app"
        # Rimuovi trailing slash
        self.base_url = self.base_url.rstrip('/')
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica stato processor"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore health_check: {e}")
            return {
                "status": "unreachable",
                "error": str(e)
            }
    
    async def process_movement(
        self,
        telegram_id: int,
        business_name: str,
        wine_name: str,
        movement_type: str,
        quantity: int
    ) -> Dict[str, Any]:
        """Processa movimento inventario (consumo/rifornimento)"""
        logger.info(
            f"[PROCESSOR_CLIENT] process_movement called | "
            f"telegram_id={telegram_id}, business={business_name}, "
            f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity}"
        )
        try:
            data = aiohttp.FormData()
            data.add_field('telegram_id', str(telegram_id))
            data.add_field('business_name', business_name)
            data.add_field('wine_name', wine_name)
            data.add_field('movement_type', movement_type)
            data.add_field('quantity', str(quantity))
            
            logger.debug(f"[PROCESSOR_CLIENT] Sending POST to {self.base_url}/process-movement")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/process-movement",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_text = await response.text()
                    logger.debug(
                        f"[PROCESSOR_CLIENT] Response status={response.status} | "
                        f"telegram_id={telegram_id}, wine_name='{wine_name}' | "
                        f"response_preview={response_text[:200]}"
                    )
                    
                    if response.status == 200:
                        try:
                            result = await response.json()
                            logger.info(
                                f"[PROCESSOR_CLIENT] process_movement success | "
                                f"telegram_id={telegram_id}, wine_name='{wine_name}', "
                                f"job_id={result.get('job_id')}, status={result.get('status')}"
                            )
                            return result
                        except Exception as json_error:
                            logger.error(
                                f"[PROCESSOR_CLIENT] Failed to parse JSON response | "
                                f"telegram_id={telegram_id}, wine_name='{wine_name}' | "
                                f"response_text={response_text[:500]} | error={json_error}",
                                exc_info=True
                            )
                            return {
                                "status": "error",
                                "error": f"Failed to parse response: {str(json_error)}",
                                "error_message": f"Failed to parse response: {str(json_error)}"
                            }
                    else:
                        logger.error(
                            f"[PROCESSOR_CLIENT] HTTP error {response.status} | "
                            f"telegram_id={telegram_id}, business={business_name}, "
                            f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity} | "
                            f"response_text={response_text[:500]}"
                        )
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {response_text[:200]}",
                            "error_message": f"HTTP {response.status}: {response_text[:200]}"
                        }
        except asyncio.TimeoutError as te:
            logger.error(
                f"[PROCESSOR_CLIENT] Timeout calling processor | "
                f"telegram_id={telegram_id}, business={business_name}, "
                f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity}",
                exc_info=True
            )
            return {
                "status": "error",
                "error": f"Timeout calling processor: {str(te)}",
                "error_message": f"Timeout calling processor: {str(te)}"
            }
        except aiohttp.ClientError as ce:
            logger.error(
                f"[PROCESSOR_CLIENT] HTTP client error | "
                f"telegram_id={telegram_id}, business={business_name}, "
                f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity} | "
                f"error={str(ce)}",
                exc_info=True
            )
            return {
                "status": "error",
                "error": f"HTTP client error: {str(ce)}",
                "error_message": f"HTTP client error: {str(ce)}"
            }
        except Exception as e:
            logger.error(
                f"[PROCESSOR_CLIENT] Unexpected error in process_movement | "
                f"telegram_id={telegram_id}, business={business_name}, "
                f"wine_name='{wine_name}', movement_type={movement_type}, quantity={quantity} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}",
                "error_message": f"Unexpected error: {str(e)}"
            }
    
    async def process_inventory(
        self,
        telegram_id: int,
        business_name: str,
        file_type: str,
        file_content: bytes,
        file_name: str,
        client_msg_id: str = None,
        correlation_id: str = None,
        mode: str = "add",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Processa file inventario"""
        try:
            data = aiohttp.FormData()
            data.add_field('telegram_id', str(telegram_id))
            data.add_field('business_name', business_name)
            data.add_field('file_type', file_type)
            data.add_field('mode', mode)
            data.add_field('dry_run', str(dry_run).lower())
            
            if client_msg_id:
                data.add_field('client_msg_id', client_msg_id)
            if correlation_id:
                data.add_field('correlation_id', correlation_id)
            
            # Aggiungi file
            data.add_field('file', file_content, filename=file_name, content_type='application/octet-stream')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/process-inventory",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"[PROCESSOR_CLIENT] Errore process_inventory: HTTP {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore process_inventory: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """Crea tabelle utente nel processor"""
        try:
            data = aiohttp.FormData()
            data.add_field('telegram_id', str(telegram_id))
            data.add_field('business_name', business_name)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/create-tables",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"[PROCESSOR_CLIENT] Errore create_tables: HTTP {response.status} - {error_text}")
                        return {
                            "status": "error",
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore create_tables: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def delete_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """Cancella tabelle utente nel processor"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.base_url}/tables/{telegram_id}",
                    params={"business_name": business_name},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"[PROCESSOR_CLIENT] Errore delete_tables: HTTP {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore delete_tables: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Ottieni stato job"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/status/{job_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        return {
                            "status": "unknown",
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore get_job_status: {e}")
            return {
                "status": "unknown",
                "error": str(e)
            }
    
    async def wait_for_job_completion(
        self,
        job_id: str,
        max_wait_seconds: int = 3600,
        poll_interval: int = 10
    ) -> Dict[str, Any]:
        """Attendi completamento job con polling"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_seconds:
                return {
                    "status": "timeout",
                    "error": f"Job {job_id} non completato entro {max_wait_seconds}s"
                }
            
            status = await self.get_job_status(job_id)
            
            if status.get("status") == "completed":
                return status
            elif status.get("status") == "failed":
                return status
            elif status.get("status") == "processing" or status.get("status") == "pending":
                # Attendi prima del prossimo poll
                await asyncio.sleep(poll_interval)
            else:
                # Stato sconosciuto, attendi comunque
                await asyncio.sleep(poll_interval)
    
    async def update_wine_field(
        self,
        telegram_id: int,
        business_name: str,
        wine_id: int,
        field: str,
        value: str
    ) -> Dict[str, Any]:
        """Aggiorna campo vino"""
        try:
            data = aiohttp.FormData()
            data.add_field('telegram_id', str(telegram_id))
            data.add_field('business_name', business_name)
            data.add_field('wine_id', str(wine_id))
            data.add_field('field', field)
            data.add_field('value', value)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/update-wine-field",
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"[PROCESSOR_CLIENT] Errore update_wine_field: HTTP {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore update_wine_field: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }


# Istanza globale
processor_client = ProcessorClient()



