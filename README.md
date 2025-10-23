# Gio.ia Bot - Assistente AI per Gestione Inventario Vini

Un bot Telegram intelligente per la gestione dell'inventario di vini con AI conversazionale e microservizio processor integrato.

## 🚀 Funzionalità

- **AI Conversazionale** - Chat intelligente con GPT-3.5-turbo
- **Gestione Inventario** - Tracking vini in tempo reale
- **Movimenti** - Registrazione vendite e rifornimenti
- **Alert Scorte** - Notifiche automatiche per scorte basse
- **Backup** - Salvataggio periodico inventario
- **Report** - Statistiche e analisi consumi
- **Onboarding AI** - Setup guidato dall'AI
- **Processor Microservice** - Elaborazione file CSV/Excel e OCR

## 📋 Comandi Principali

- `/start` - Avvia il bot
- `/help` - Mostra comandi disponibili
- `/inventario` - Visualizza inventario completo
- `/log` - Mostra movimenti recenti
- `/backup` - Crea backup inventario
- `/stats` - Statistiche e report

## 🔧 Setup

### Prerequisiti
- Python 3.8+
- PostgreSQL
- Token Telegram Bot
- OpenAI API Key
- **Gioia Processor** (microservizio separato)

### Installazione
```bash
git clone https://github.com/gioiasoftware-pixel/Gio.ia-bot.git
cd Gio.ia-bot
pip install -r requirements.txt
```

### Configurazione
Copia `.env.example` in `.env` e configura:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://user:pass@host:port/db
PROCESSOR_URL=https://your-processor.railway.app
```

**Nota**: `PROCESSOR_URL` deve puntare al microservizio Gioia Processor deployato su Railway.

### Avvio
```bash
python -m src.bot
```

## 🧪 Test Integrazione

### **Comandi di Test**
- `/testai` - Test connessione OpenAI API
- `/testprocessor` - Test connessione microservizio processor

### **Verifica Configurazione**
```bash
# Test locale processor
curl http://localhost:8001/health

# Test bot-processor
curl -X POST http://localhost:8001/process-inventory \
  -F "telegram_id=123456" \
  -F "business_name=Test" \
  -F "file_type=csv" \
  -F "file=@test.csv"
```

## 🏗️ Architettura Microservizi

```
┌─────────────────┐    HTTP    ┌─────────────────┐
│   TELEGRAM BOT  │ ────────► │   PROCESSOR     │
│   (Porta 8000)  │           │   (Porta 8001)  │
│   python-telegram-bot │     │   FastAPI       │
└─────────────────┘           └─────────────────┘
        │                              │
        ▼                              ▼
┌─────────────────┐           ┌─────────────────┐
│   PostgreSQL    │           │   PostgreSQL    │
│   (Database)    │           │   (Database)    │
└─────────────────┘           └─────────────────┘
```

### **Comunicazione Bot ↔ Processor**
1. **Bot** riceve file inventario da utente
2. **Bot** invia file al processor via `POST /process-inventory`
3. **Processor** elabora file e salva nel database
4. **Processor** restituisce conferma al bot
5. **Bot** notifica utente del completamento

## 📁 Struttura Progetto

```
gioia-project/
├── telegram-ai-bot/          # Bot principale
│   ├── src/
│   │   ├── bot.py            # Handler Telegram
│   │   ├── ai.py             # Integrazione OpenAI
│   │   ├── database.py       # Database bot
│   │   ├── new_onboarding.py # Onboarding AI
│   │   └── file_upload.py    # Gestione upload
│   ├── requirements.txt      # Dipendenze bot
│   ├── Procfile             # Deploy Railway
│   └── README.md            # Documentazione bot
├── gioia-processor/          # Microservizio processor
│   ├── main.py              # FastAPI application
│   ├── csv_processor.py     # Parsing CSV/Excel
│   ├── ocr_processor.py     # OCR immagini
│   ├── database.py          # Database processor
│   ├── requirements.txt     # Dipendenze processor
│   └── README.md           # Documentazione processor
└── README2.md              # Guida processor completa
```

### **Sviluppo Locale**
```bash
# Apri entrambi i progetti in Cursor
cursor gioia-project/

# Sviluppa bot
cd telegram-ai-bot/
python -m src.bot

# Sviluppa processor (in terminale separato)
cd gioia-processor/
python start_processor.py
```

## 🌐 Deploy

### **Deploy Bot (telegram-ai-bot)**
1. **Railway Dashboard** → New Project
2. **Connetti repository** `telegram-ai-bot`
3. **Configura variabili**:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token
   OPENAI_API_KEY=your_openai_key
   DATABASE_URL=postgresql://user:pass@host:port/db
   PROCESSOR_URL=https://your-processor.railway.app
   ```
4. **Deploy automatico**

### **Deploy Processor (gioia-processor)**
1. **Railway Dashboard** → New Project
2. **Connetti repository** `gioia-processor`
3. **Configura variabili**:
   ```env
   DATABASE_URL=postgresql://user:pass@host:port/db
   PORT=8001
   ```
4. **Deploy automatico**

### **Configurazione Finale**
1. **Ottieni URL processor** da Railway
2. **Aggiorna PROCESSOR_URL** nel bot
3. **Testa integrazione** con `/testprocessor`

### **Sviluppo Locale Completo**
```bash
# Terminale 1 - Bot
cd telegram-ai-bot/
python -m src.bot

# Terminale 2 - Processor
cd gioia-processor/
python start_processor.py

# Test integrazione
curl http://localhost:8001/health
```

## 💻 Sviluppo con Cursor

### **Setup Progetto Unificato**
```bash
# Crea cartella principale
mkdir gioia-project
cd gioia-project

# Clona entrambi i repository
git clone https://github.com/your-username/telegram-ai-bot.git
git clone https://github.com/your-username/gioia-processor.git

# Apri tutto in Cursor
cursor .
```

### **Struttura Cursor**
```
gioia-project/
├── telegram-ai-bot/          # Bot principale
│   ├── src/                  # Codice bot
│   ├── requirements.txt      # Dipendenze bot
│   └── README.md            # Documentazione
├── gioia-processor/          # Microservizio
│   ├── main.py              # FastAPI app
│   ├── requirements.txt     # Dipendenze processor
│   └── README.md           # Documentazione
└── README2.md              # Guida processor completa
```

### **Comandi Sviluppo**
```bash
# Avvia bot (Terminale 1)
cd telegram-ai-bot/
python -m src.bot

# Avvia processor (Terminale 2)
cd gioia-processor/
python start_processor.py

# Test integrazione
curl http://localhost:8001/health
curl http://localhost:8000/health
```

### **Debug Integrato**
- **Bot logs**: Terminale 1
- **Processor logs**: Terminale 2
- **Database**: PostgreSQL Railway
- **API calls**: Monitora con `/testprocessor`

## 🚀 Workflow Completo

### **1. Setup Iniziale**
```bash
# Crea progetto unificato
mkdir gioia-project
cd gioia-project

# Clona repository
git clone https://github.com/your-username/telegram-ai-bot.git
git clone https://github.com/your-username/gioia-processor.git

# Apri in Cursor
cursor .
```

### **2. Sviluppo Locale**
```bash
# Terminale 1 - Bot
cd telegram-ai-bot/
python -m src.bot

# Terminale 2 - Processor
cd gioia-processor/
python start_processor.py
```

### **3. Deploy Railway**
1. **Deploy processor** → Ottieni URL
2. **Deploy bot** → Configura PROCESSOR_URL
3. **Test integrazione** → `/testprocessor`

### **4. Monitoraggio**
- **Railway Dashboard** → Logs entrambi i servizi
- **Bot Telegram** → `/testprocessor` per test
- **Health checks** → Endpoint `/health`

### **5. Sviluppo Continuo**
- **Modifiche bot** → Push → Deploy automatico
- **Modifiche processor** → Push → Deploy automatico
- **Test integrazione** → `/testprocessor`

## 📊 Architettura

```
┌─────────────────┐    HTTP    ┌─────────────────┐
│   FRONT (Bot)   │ ────────► │   PROCESSOR     │
│   Porta: 8000   │           │   Porta: 8001   │
│   Telegram API  │           │   FastAPI       │
└─────────────────┘           └─────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐           ┌─────────────────┐
│   PostgreSQL    │           │   PostgreSQL    │
│   (Database)    │           │   (Database)    │
└─────────────────┘           └─────────────────┘
```

**Nota:** Il processor è un microservizio separato con repository dedicato.

## 🧠 AI Features

- **Conversazione Naturale** - Chat fluida in italiano
- **Analisi Inventario** - Suggerimenti intelligenti
- **Rilevamento Pattern** - Identifica trend di consumo
- **Consigli Proattivi** - Suggerimenti per riordini
- **Onboarding Guidato** - Setup assistito dall'AI

## 📈 Stack Tecnologico

- **Backend:** Python, FastAPI, SQLAlchemy
- **Database:** PostgreSQL
- **AI:** OpenAI GPT-3.5-turbo
- **Bot:** python-telegram-bot
- **Deploy:** Railway
- **Architettura:** Microservizi

## 🔗 Moduli Principali

- `src/bot.py` - Handler principale Telegram
- `src/ai.py` - Integrazione OpenAI
- `src/database.py` - Gestione database
- `src/onboarding.py` - Processo setup utente
- `src/new_onboarding.py` - Onboarding AI-guidato
- `src/file_upload.py` - Gestione upload file

**Nota:** Il microservizio processor è in un repository separato.

## 🚀 Roadmap

- [x] Bot Telegram base
- [x] Integrazione AI
- [x] Database PostgreSQL
- [x] Gestione inventario
- [x] Sistema movimenti
- [x] Alert scorte
- [x] Backup automatico
- [x] Onboarding AI
- [x] Architettura microservizi
- [ ] Dashboard web
- [ ] API REST completa
- [ ] Integrazione POS
- [ ] Analytics avanzate

## 📞 Supporto

Per supporto tecnico o domande:
- **GitHub Issues:** [Issues](https://github.com/gioiasoftware-pixel/Gio.ia-bot/issues)
- **Email:** support@gioiasoftware.com

## 📄 Licenza

MIT License - Vedi [LICENSE](LICENSE) per dettagli.

---

**Gio.ia Bot** - Trasforma la gestione del tuo inventario vini con l'AI! 🍷🤖