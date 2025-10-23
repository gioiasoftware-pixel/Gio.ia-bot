#!/usr/bin/env python3
"""
Script di avvio per il microservizio processor
"""
import uvicorn
import os
import logging

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    port = int(os.getenv("PROCESSOR_PORT", 8001))
    logger.info(f"🚀 Avvio microservizio processor su porta {port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )