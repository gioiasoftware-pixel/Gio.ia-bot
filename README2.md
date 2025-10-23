# 🍷 Gioia Processor - Microservizio Elaborazione Inventari

## 📋 Panoramica

**Gioia Processor** è un microservizio FastAPI dedicato all'elaborazione di file inventari per il sistema Gioia. Gestisce parsing di file CSV/Excel e riconoscimento OCR da immagini per estrarre dati sui vini.

## 🔗 Integrazione con Telegram Bot

Il processor è progettato per comunicare con il **telegram-ai-bot** tramite HTTP API. Il bot invia file inventari al processor e riceve conferme di elaborazione.

### **Flusso di Comunicazione:**
1. **Bot** riceve file inventario da utente
2. **Bot** invia file al processor via `POST /process-inventory`
3. **Processor** elabora file e salva nel database
4. **Processor** restituisce conferma al bot
5. **Bot** notifica utente del completamento

## 🏗️ Architettura

```
┌─────────────────┐    HTTP    ┌─────────────────┐
│   TELEGRAM BOT  │ ────────► │   PROCESSOR     │
│   (Porta 8000)  │           │   (Porta 8001)  │
│   python-telegram-bot │     │   FastAPI       │
└─────────────────┘           └─────────────────┘
                                        │
                                        ▼
                               ┌─────────────────┐
                               │   PostgreSQL    │
                               │   (Database)    │
                               └─────────────────┘
```

## 🚀 Funzionalità

### **File Processing**
- **CSV**: Parsing file CSV con pattern matching intelligente
- **Excel**: Supporto file Excel (.xlsx, .xls) con openpyxl
- **OCR**: Riconoscimento testo da immagini inventari con Tesseract

### **API Endpoints**
- `GET /health` - Health check del servizio
- `POST /process-inventory` - Elabora file inventario
- `GET /status/{telegram_id}` - Stato elaborazione utente

### **Database Integration**
- Connessione PostgreSQL con SQLAlchemy
- Modelli per inventari e vini
- Gestione transazioni e backup

## 📁 Struttura Progetto

```
gioia-processor/
├── main.py                 # FastAPI application
├── csv_processor.py        # Logica parsing CSV/Excel
├── ocr_processor.py       # Logica OCR immagini
├── database.py            # Connessione e modelli DB
├── requirements.txt       # Dipendenze Python
├── start_processor.py     # Script avvio servizio
├── Procfile              # Configurazione deploy Railway
├── railway.json          # Config Railway
└── README.md             # Documentazione
```

## 🔧 File da Creare

### **1. main.py** - FastAPI Application
```python
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

app = FastAPI(title="Gioia Processor", version="1.0.0")

# CORS per comunicazione con bot
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "gioia-processor"}

@app.post("/process-inventory")
async def process_inventory(
    telegram_id: int = Form(...),
    business_name: str = Form(...),
    file_type: str = Form(...),
    file: UploadFile = File(...)
):
    # Logica elaborazione inventario
    # Restituisce: {"status": "success", "total_wines": N, "business_name": "...", "telegram_id": ...}
    pass

@app.get("/status/{telegram_id}")
async def get_status(telegram_id: int):
    # Restituisce stato elaborazione per utente
    pass

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### **2. requirements.txt** - Dipendenze
```
fastapi>=0.110.0
uvicorn>=0.27.0
openpyxl>=3.1.2
pytesseract>=0.3.10
Pillow>=10.1.0
sqlalchemy>=2.0.23
psycopg2-binary>=2.9.9
python-multipart>=0.0.6
```

### **3. Procfile** - Deploy Railway
```
web: python start_processor.py
```

### **4. start_processor.py** - Script Avvio
```python
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
```

### **5. railway.json** - Config Railway
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python start_processor.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

## 🔧 Installazione e Deploy

### **1. Setup Locale**
```bash
# Clona repository
git clone <repository-url>
cd gioia-processor

# Installa dipendenze
pip install -r requirements.txt

# Configura variabili ambiente
export DATABASE_URL="postgresql://user:pass@host:port/db"
export PORT=8001

# Avvia servizio
python start_processor.py
```

### **2. Deploy Railway - GUIDA COMPLETA**

#### **STEP 1: Preparazione Repository**
```bash
# 1. Crea repository GitHub
# Vai su GitHub.com → New Repository
# Nome: gioia-processor
# Descrizione: Microservizio elaborazione inventari Gioia
# Pubblica come pubblico

# 2. Clona e configura
git clone https://github.com/tuo-username/gioia-processor.git
cd gioia-processor

# 3. Crea tutti i file (vedi sezione "File da Creare" sopra)
# 4. Commit e push
git add .
git commit -m "Initial commit: Gioia Processor microservice"
git push origin main
```

#### **STEP 2: Deploy su Railway**
1. **Vai su Railway.app** e fai login
2. **Clicca "New Project"**
3. **Seleziona "Deploy from GitHub repo"**
4. **Connetti il repository `gioia-processor`**
5. **Railway rileva automaticamente** il progetto Python

#### **STEP 3: Configurazione Variabili Ambiente**
Nel dashboard Railway del progetto:

```env
# Variabili obbligatorie
DATABASE_URL=postgresql://user:pass@host:port/db
PORT=8001

# Variabili opzionali
PYTHON_VERSION=3.11
```

**Come ottenere DATABASE_URL:**
1. **Crea database PostgreSQL** su Railway
2. **Clicca sul database** → Settings → Connect
3. **Copia la stringa di connessione** completa
4. **Incolla in DATABASE_URL**

#### **STEP 4: Configurazione Deploy**
Railway dovrebbe rilevare automaticamente:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python start_processor.py`
- **Port**: 8001

Se non rileva, configura manualmente:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python start_processor.py`

#### **STEP 5: Verifica Deploy**
1. **Attendi deploy completato** (2-3 minuti)
2. **Clicca sul dominio** generato da Railway
3. **Testa endpoint**: `https://your-app.railway.app/health`
4. **Dovrebbe restituire**: `{"status": "healthy", "service": "gioia-processor"}`

#### **STEP 6: Configurazione Bot**
Nel bot principale, aggiorna:
```env
PROCESSOR_URL=https://your-app.railway.app
```

#### **STEP 7: Test Integrazione**
```bash
# Test health check
curl https://your-app.railway.app/health

# Test processamento (esempio)
curl -X POST https://your-app.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test Restaurant" \
  -F "file_type=csv" \
  -F "file=@test.csv"
```

### **3. Test Deploy**
```bash
# Health check
curl https://your-app.railway.app/health

# Test processamento (esempio)
curl -X POST https://your-app.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test Restaurant" \
  -F "file_type=csv" \
  -F "file=@test.csv"
```

## 🔗 Configurazione Bot

### **Variabile Ambiente Bot**
Nel bot principale, configura:
```env
PROCESSOR_URL=https://your-processor.railway.app
```

### **URL Endpoints**
- **Health**: `GET /health`
- **Process**: `POST /process-inventory`
- **Status**: `GET /status/{telegram_id}`

## 📊 Modelli Database

### **Inventario**
- `id`: Primary key
- `telegram_id`: ID utente Telegram
- `business_name`: Nome locale/azienda
- `created_at`: Timestamp creazione
- `status`: Stato elaborazione

### **Vino**
- `id`: Primary key
- `inventory_id`: FK verso inventario
- `name`: Nome vino
- `vintage`: Annata
- `producer`: Produttore
- `region`: Regione
- `price`: Prezzo
- `quantity`: Quantità
- `wine_type`: Tipo vino (rosso/bianco/rosato/spumante)

## 🔄 Flusso Elaborazione

1. **Ricezione File**: Bot invia file al processor
2. **Parsing**: Estrazione dati da CSV/Excel o OCR
3. **Validazione**: Controllo e pulizia dati
4. **Salvataggio**: Inserimento nel database
5. **Conferma**: Notifica completamento al bot

## 🛠️ Sviluppo

### **Test Locale**
```bash
# Avvia server sviluppo
uvicorn main:app --reload --port 8001

# Test health check
curl http://localhost:8001/health
```

### **Deploy Railway**
1. Connetti repository GitHub
2. Configura variabili ambiente
3. Deploy automatico

## 📈 Monitoraggio

### **Logs**
- Elaborazione file
- Errori parsing
- Performance OCR
- Connessioni database

### **Metriche**
- File processati
- Tempo elaborazione
- Success rate
- Errori per tipo

## 🔒 Sicurezza

- **CORS**: Configurato per comunicazione bot
- **Validazione**: Controllo input file
- **Error Handling**: Gestione errori robusta
- **Rate Limiting**: (da implementare)

## 🚀 Roadmap

- [ ] Cache Redis per performance
- [ ] Rate limiting API
- [ ] Monitoring avanzato
- [ ] Supporto più formati file
- [ ] OCR migliorato con AI
- [ ] Batch processing

## 🔧 Troubleshooting Railway

### **Problemi Comuni**

#### **1. Deploy Fallisce**
```bash
# Controlla logs su Railway dashboard
# Errori comuni:
- requirements.txt mancante
- start_processor.py non trovato
- DATABASE_URL non configurato
```

#### **2. Database Connection Error**
```bash
# Verifica DATABASE_URL
echo $DATABASE_URL

# Test connessione locale
psql $DATABASE_URL -c "SELECT 1;"
```

#### **3. Port Binding Error**
```bash
# Verifica che PORT sia configurato
# Railway dovrebbe impostarlo automaticamente
# Se manuale: export PORT=8001
```

#### **4. Dependencies Error**
```bash
# Aggiorna requirements.txt
pip freeze > requirements.txt

# Verifica versioni compatibili
pip install --upgrade -r requirements.txt
```

### **Monitoraggio Railway**

#### **Logs in Tempo Reale**
1. **Railway Dashboard** → Progetto → Logs
2. **Filtra per livello**: ERROR, WARN, INFO
3. **Monitora**: Connessioni DB, API calls, Errori

#### **Metriche Performance**
- **CPU Usage**: Monitora utilizzo risorse
- **Memory**: Controlla consumo RAM
- **Response Time**: Tempo risposta API
- **Error Rate**: Percentuale errori

#### **Health Check Automatico**
Railway monitora automaticamente:
- **Endpoint**: `/health`
- **Timeout**: 30 secondi
- **Retry**: 3 tentativi
- **Restart**: Automatico su failure

## 📞 Supporto

Per problemi o domande:
- **Repository**: `gioia-processor`
- **Logs**: Railway dashboard → Logs
- **Database**: Railway PostgreSQL dashboard
- **Bot Integration**: Usa `/testprocessor` nel bot

### **Comandi Debug**
```bash
# Test locale
python start_processor.py

# Test endpoint
curl http://localhost:8001/health

# Test database
python -c "from database import db; print('DB OK')"
```

## ✅ CHECKLIST DEPLOY COMPLETO

### **Pre-Deploy**
- [ ] Repository GitHub creato (`gioia-processor`)
- [ ] Tutti i file creati (main.py, requirements.txt, etc.)
- [ ] Codice committato e pushato su GitHub
- [ ] Test locale funzionante

### **Deploy Railway**
- [ ] Progetto Railway creato
- [ ] Repository GitHub connesso
- [ ] Database PostgreSQL creato
- [ ] Variabili ambiente configurate
- [ ] Deploy completato con successo

### **Post-Deploy**
- [ ] Health check funzionante (`/health`)
- [ ] Database connesso
- [ ] URL processor ottenuto
- [ ] Bot principale aggiornato con PROCESSOR_URL
- [ ] Test integrazione bot-processor

### **Verifica Finale**
- [ ] `/testprocessor` nel bot restituisce successo
- [ ] Upload file inventario funziona
- [ ] Elaborazione file completata
- [ ] Dati salvati nel database
- [ ] Notifica utente ricevuta

## 🔍 CHECK COMPLETO POST-DEPLOY

### **STEP 1: Verifica Processor Attivo**
```bash
# Test endpoint base
curl https://your-processor.railway.app/

# Test health check
curl https://your-processor.railway.app/health

# Risposta attesa:
# {"status": "healthy", "service": "gioia-processor"}
```

### **STEP 2: Controlla Logs Railway**
1. **Railway Dashboard** → Progetto processor → Logs
2. **Cerca errori**:
   - `ModuleNotFoundError`
   - `Database connection failed`
   - `Port binding error`
   - `Import error`

### **STEP 3: Verifica Database**
```bash
# Test connessione database
# Nel processor, verifica che DATABASE_URL sia configurato
echo $DATABASE_URL

# Dovrebbe restituire URL PostgreSQL completo
```

### **STEP 4: Test Endpoint Processor**
```bash
# Test processamento (esempio)
curl -X POST https://your-processor.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test Restaurant" \
  -F "file_type=csv" \
  -F "file=@test.csv"

# Risposta attesa:
# {"status": "success", "total_wines": N, "business_name": "...", "telegram_id": ...}
```

### **STEP 5: Configurazione Bot**
Nel bot principale, aggiungi variabile:
```env
PROCESSOR_URL=https://your-processor.railway.app
```

### **STEP 6: Test Integrazione Bot**
1. **Nel bot Telegram**: `/testprocessor`
2. **Dovrebbe restituire**:
   ```
   ✅ Processor connesso!
   
   URL: https://your-processor.railway.app
   Status: healthy
   Service: gioia-processor
   ```

## 🚨 TROUBLESHOOTING AVANZATO

### **Errore 404 - Processor non raggiungibile**
```bash
# Possibili cause:
1. Processor non deployato
2. Endpoint /health non implementato
3. Porta sbagliata
4. Database non connesso

# Soluzioni:
1. Controlla logs Railway processor
2. Verifica che main.py sia presente
3. Controlla che start_processor.py esista
4. Verifica DATABASE_URL configurato
```

### **Errore 500 - Internal Server Error**
```bash
# Possibili cause:
1. Database non connesso
2. Dipendenze mancanti
3. Errori nel codice

# Soluzioni:
1. Controlla logs per errori specifici
2. Verifica requirements.txt
3. Testa connessione database
4. Controlla sintassi codice
```

### **Errore Timeout**
```bash
# Possibili cause:
1. Database lento
2. OCR processing lungo
3. File troppo grande

# Soluzioni:
1. Ottimizza query database
2. Riduci dimensione file
3. Aumenta timeout Railway
```

### **Errore Import/Dependencies**
```bash
# Possibili cause:
1. requirements.txt mancante
2. Versioni incompatibili
3. Python version sbagliata

# Soluzioni:
1. Verifica requirements.txt
2. Controlla Python version
3. Aggiorna dipendenze
```

## 📊 MONITORAGGIO CONTINUO

### **Metriche da Monitorare**
- **Response Time**: < 5 secondi per /health
- **Error Rate**: < 1% errori
- **Memory Usage**: < 512MB
- **CPU Usage**: < 50%

### **Alert da Configurare**
- **Health check failed** per > 1 minuto
- **Error rate** > 5%
- **Memory usage** > 80%
- **Response time** > 10 secondi

### **Logs da Monitorare**
- **Database connections**
- **API calls** al processor
- **Error rates** per endpoint
- **Performance metrics**

## 🔧 CONFIGURAZIONE AVANZATA

### **Variabili Ambiente Processor**
```env
# Obbligatorie
DATABASE_URL=postgresql://user:pass@host:port/db
PORT=8001

# Opzionali
PYTHON_VERSION=3.11
LOG_LEVEL=INFO
MAX_FILE_SIZE=10MB
OCR_TIMEOUT=30
```

### **Configurazione Railway Avanzata**
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python start_processor.py",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### **Test di Carico**
```bash
# Test multiple richieste
for i in {1..10}; do
  curl https://your-processor.railway.app/health
done

# Test file grandi
curl -X POST https://your-processor.railway.app/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test" \
  -F "file_type=csv" \
  -F "file=@large_file.csv"
```

---

**Nota**: Questo microservizio è completamente separato dal bot Telegram e gestisce solo l'elaborazione dei file inventari.
