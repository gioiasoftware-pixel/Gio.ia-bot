#!/usr/bin/env python3
"""
Script di avvio per il microservizio processor
"""
import os
import sys
import uvicorn
from main import app

if __name__ == "__main__":
    # Porta del processor (diversa dal bot principale)
    port = int(os.getenv("PROCESSOR_PORT", 8001))
    
    print(f"🚀 Avvio microservizio processor su porta {port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
