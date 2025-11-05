import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from src.processor_client import ProcessorClient


class TestProcessorIntegration:
    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        client = ProcessorClient(base_url="https://processor.local")
        
        async def mock_json():
            return {"status": "healthy"}
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = mock_json
        
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_response
        
        with patch("aiohttp.ClientSession.get", return_value=mock_ctx):
            result = await client.health_check()
            assert result.get("status") == "healthy"

    @pytest.mark.asyncio
    async def test_process_movement_success(self):
        client = ProcessorClient(base_url="https://processor.local")
        
        async def mock_text():
            return '{"status":"processing","job_id":"job-123"}'
        async def mock_json():
            return {"status": "processing", "job_id": "job-123"}
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = mock_text
        mock_response.json = mock_json
        
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_response
        
        with patch("aiohttp.ClientSession.post", return_value=mock_ctx):
            res = await client.process_movement(
                telegram_id=1,
                business_name="Test",
                wine_name="Chianti",
                movement_type="consumo",
                quantity=2,
            )
            assert res.get("status") in ["processing", "success", "completed"]
            assert "job_id" in res

    @pytest.mark.asyncio
    async def test_process_inventory_success(self):
        client = ProcessorClient(base_url="https://processor.local")
        
        async def mock_json():
            return {"status": "processing", "job_id": "job-456"}
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = mock_json
        
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_response
        
        with patch("aiohttp.ClientSession.post", return_value=mock_ctx):
            res = await client.process_inventory(
                telegram_id=1,
                business_name="Test",
                file_type="csv",
                file_content=b"Nome,Cantina\nChianti,Barone",
                file_name="test.csv",
                client_msg_id="abc",
            )
            assert res.get("status") in ["processing", "success", "completed"]

    @pytest.mark.asyncio
    async def test_get_job_status_completed(self):
        client = ProcessorClient(base_url="https://processor.local")
        
        async def mock_json():
            return {"status": "completed", "job_id": "job-123"}
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = mock_json
        
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_response
        
        with patch("aiohttp.ClientSession.get", return_value=mock_ctx):
            res = await client.get_job_status("job-123")
            assert res.get("status") == "completed"
