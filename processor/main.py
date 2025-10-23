"""
Microservizio per elaborazione inventario
Gestisce OCR, parsing CSV/Excel e salvataggio nel database
"""
import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import db_manager
from ocr_processor import OCRProcessor
from csv_processor import CSVProcessor

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Inventory Processor", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Processori
ocr_processor = OCRProcessor()
csv_processor = CSVProcessor()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/process-inventory")
async def process_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file_type: str = Form(...),  # 'csv', 'excel', 'photo'
    file: UploadFile = File(...)
):
    """
    Elabora un file inventario e salva i dati nel database
    
    Args:
        telegram_id: ID Telegram dell'utente
        business_name: Nome del locale
        file_type: Tipo file ('csv', 'excel', 'photo')
        file: File da elaborare
    
    Returns:
        Risultato dell'elaborazione
    """
    try:
        logger.info(f"Elaborazione inventario per {business_name} (ID: {telegram_id})")
        
        # Leggi il file
        file_content = await file.read()
        file_name = file.filename
        
        # Elabora in base al tipo
        if file_type == 'photo':
            wines = await ocr_processor.process_photo(file_content, file_name)
        elif file_type in ['csv', 'excel']:
            wines = await csv_processor.process_file(file_content, file_name, file_type)
        else:
            raise HTTPException(status_code=400, detail="Tipo file non supportato")
        
        # Salva i vini nel database
        saved_wines = []
        for wine_data in wines:
            try:
                wine = db_manager.add_wine(telegram_id, wine_data)
                if wine:
                    saved_wines.append({
                        'id': wine.id,
                        'name': wine.name,
                        'producer': wine.producer,
                        'quantity': wine.quantity
                    })
            except Exception as e:
                logger.error(f"Errore salvataggio vino {wine_data.get('name', 'Unknown')}: {e}")
        
        # Crea backup inventario
        backup_data = {
            'business_name': business_name,
            'file_name': file_name,
            'file_type': file_type,
            'processed_date': datetime.utcnow().isoformat(),
            'total_wines': len(saved_wines),
            'wines': saved_wines
        }
        
        db_manager.create_inventory_backup(
            telegram_id=telegram_id,
            backup_name="Inventario Giorno 0",
            backup_data=json.dumps(backup_data),
            backup_type="initial"
        )
        
        logger.info(f"Elaborazione completata: {len(saved_wines)} vini salvati per {business_name}")
        
        return {
            "success": True,
            "business_name": business_name,
            "total_wines": len(saved_wines),
            "wines": saved_wines,
            "message": f"Inventario di {business_name} elaborato con successo!"
        }
        
    except Exception as e:
        logger.error(f"Errore elaborazione inventario: {e}")
        raise HTTPException(status_code=500, detail=f"Errore elaborazione: {str(e)}")

@app.get("/status/{telegram_id}")
async def get_user_status(telegram_id: int):
    """Ottieni status utente e inventario"""
    try:
        user = db_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        
        wines = db_manager.get_user_wines(telegram_id)
        stats = db_manager.get_user_stats(telegram_id)
        
        return {
            "user": {
                "telegram_id": user.telegram_id,
                "business_name": user.business_name,
                "onboarding_completed": user.onboarding_completed
            },
            "inventory": {
                "total_wines": stats.get("total_wines", 0),
                "total_quantity": stats.get("total_quantity", 0),
                "low_stock_count": stats.get("low_stock_count", 0)
            },
            "wines": [
                {
                    "id": wine.id,
                    "name": wine.name,
                    "producer": wine.producer,
                    "quantity": wine.quantity,
                    "min_quantity": wine.min_quantity
                }
                for wine in wines
            ]
        }
        
    except Exception as e:
        logger.error(f"Errore status utente {telegram_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")

if __name__ == "__main__":
    # Avvia il server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8001)),
        reload=True
    )
