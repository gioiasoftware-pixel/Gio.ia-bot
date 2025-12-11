"""
Client per comunicare con il microservizio Gioia Processor.

Gestisce tutte le chiamate HTTP al processor per:
- Health check
- Creazione tabelle utente
- Elaborazione inventario
- Movimenti inventario
- Status job
"""
import logging
import aiohttp
from typing import Optional, Dict, Any
from .config import PROCESSOR_URL

logger = logging.getLogger(__name__)


class ProcessorClient:
    """Client per comunicare con il microservizio processor."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or PROCESSOR_URL.rstrip('/')
        logger.info(f"[PROCESSOR_CLIENT] Inizializzato con URL: {self.base_url}")
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Esegue una richiesta HTTP al processor."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore {method} {endpoint}: HTTP {e.status} - {e.message}")
            if e.status == 404:
                return {"status": "error", "error": f"Endpoint non trovato: {endpoint}"}
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except aiohttp.ClientError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore connessione {method} {endpoint}: {e}")
            return {"status": "error", "error": f"Errore connessione: {str(e)}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore inaspettato {method} {endpoint}: {e}", exc_info=True)
            return {"status": "error", "error": f"Errore inaspettato: {str(e)}"}
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica stato del processor."""
        return await self._make_request("GET", "/health")
    
    async def create_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """
        Crea tabelle utente nel processor.
        
        Args:
            telegram_id: ID Telegram dell'utente
            business_name: Nome del locale
            
        Returns:
            Dict con status e dettagli tabelle create
        """
        logger.info(f"[PROCESSOR_CLIENT] Chiamata create_tables: telegram_id={telegram_id}, business_name={business_name}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/create-tables",
                    data={
                        "telegram_id": telegram_id,
                        "business_name": business_name
                    }
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    logger.info(f"[PROCESSOR_CLIENT] create_tables successo: {result}")
                    return result
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore create_tables: HTTP {e.status} - {e.message}")
            if e.status == 404:
                return {"status": "error", "error": f"Endpoint /create-tables non trovato (404)"}
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except aiohttp.ClientError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore connessione create_tables: {e}")
            return {"status": "error", "error": f"Errore connessione: {str(e)}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore inaspettato create_tables: {e}", exc_info=True)
            return {"status": "error", "error": f"Errore inaspettato: {str(e)}"}
    
    async def process_inventory(
        self,
        telegram_id: int,
        business_name: str,
        file_type: str,
        file_content: bytes,
        file_name: str,
        client_msg_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        mode: str = "add"
    ) -> Dict[str, Any]:
        """
        Invia file inventario al processor per elaborazione.
        
        Args:
            telegram_id: ID Telegram dell'utente
            business_name: Nome del locale
            file_type: Tipo file (csv, excel, photo, pdf)
            file_content: Contenuto file in bytes
            file_name: Nome file
            client_msg_id: ID messaggio client per idempotenza
            correlation_id: ID correlazione per logging
            mode: Modalità (add o replace)
            
        Returns:
            Dict con job_id e status
        """
        logger.info(
            f"[PROCESSOR_CLIENT] process_inventory: telegram_id={telegram_id}, "
            f"business_name={business_name}, file_type={file_type}, file_name={file_name}, "
            f"file_size={len(file_content)} bytes"
        )
        
        files = {"file": (file_name, file_content)}
        data = {
            "telegram_id": telegram_id,
            "business_name": business_name,
            "file_type": file_type,
            "mode": mode
        }
        if client_msg_id:
            data["client_msg_id"] = client_msg_id
        if correlation_id:
            data["correlation_id"] = correlation_id
        
        try:
            timeout = aiohttp.ClientTimeout(total=60.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                form_data = aiohttp.FormData()
                form_data.add_field('file', file_content, filename=file_name)
                for key, value in data.items():
                    form_data.add_field(key, str(value))
                
                async with session.post(
                    f"{self.base_url}/process-inventory",
                    data=form_data
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore process_inventory: HTTP {e.status} - {e.message}")
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore process_inventory: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Ottiene stato di un job di elaborazione."""
        return await self._make_request("GET", f"/status/{job_id}")
    
    async def wait_for_job_completion(
        self,
        job_id: str,
        max_wait_seconds: int = 300,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """
        Attende completamento di un job con polling.
        
        Args:
            job_id: ID del job
            max_wait_seconds: Tempo massimo di attesa
            poll_interval: Intervallo tra polling (secondi)
            
        Returns:
            Dict con risultato job o status
        """
        import asyncio
        import time
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            status = await self.get_job_status(job_id)
            
            if status.get('status') == 'completed':
                return status
            elif status.get('status') == 'error' or status.get('status') == 'failed':
                return status
            
            await asyncio.sleep(poll_interval)
        
        # Timeout
        return {
            "status": "timeout",
            "job_id": job_id,
            "error": f"Timeout dopo {max_wait_seconds} secondi"
        }
    
    async def process_movement(
        self,
        telegram_id: int,
        business_name: str,
        wine_name: str,
        movement_type: str,
        quantity: int
    ) -> Dict[str, Any]:
        """Processa un movimento inventario (consumo o rifornimento)."""
        logger.info(
            f"[PROCESSOR_CLIENT] process_movement: telegram_id={telegram_id}, "
            f"business_name={business_name}, wine_name={wine_name}, "
            f"movement_type={movement_type}, quantity={quantity}"
        )
        
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/process-movement",
                    data={
                        "telegram_id": telegram_id,
                        "business_name": business_name,
                        "wine_name": wine_name,
                        "movement_type": movement_type,
                        "quantity": quantity
                    }
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore process_movement: HTTP {e.status} - {e.message}")
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore process_movement: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def update_wine_field(
        self,
        telegram_id: int,
        business_name: str,
        wine_id: int,
        field: str,
        value: str
    ) -> Dict[str, Any]:
        """Aggiorna un campo di un vino."""
        logger.info(
            f"[PROCESSOR_CLIENT] update_wine_field: telegram_id={telegram_id}, "
            f"wine_id={wine_id}, field={field}"
        )
        
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/update-wine-field",
                    data={
                        "telegram_id": telegram_id,
                        "business_name": business_name,
                        "wine_id": wine_id,
                        "field": field,
                        "value": value
                    }
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore update_wine_field: HTTP {e.status} - {e.message}")
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore update_wine_field: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def delete_tables(self, telegram_id: int, business_name: str) -> Dict[str, Any]:
        """Elimina tabelle utente."""
        logger.info(f"[PROCESSOR_CLIENT] delete_tables: telegram_id={telegram_id}, business_name={business_name}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.delete(
                    f"{self.base_url}/tables/{telegram_id}",
                    params={"business_name": business_name}
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore delete_tables: HTTP {e.status} - {e.message}")
            return {"status": "error", "error": f"HTTP {e.status}: {e.message[:200]}"}
        except Exception as e:
            logger.error(f"[PROCESSOR_CLIENT] Errore delete_tables: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


# Istanza globale del client
processor_client = ProcessorClient()
