# Gio.ia Bot - Assistente AI per Gestione Inventario Vini

Un bot Telegram intelligente per la gestione dell'inventario di vini con AI conversazionale.

## 🚀 Funzionalità

- **AI Conversazionale** - Chat intelligente con GPT-3.5-turbo
- **Gestione Inventario** - Tracking vini in tempo reale
- **Movimenti** - Registrazione vendite e rifornimenti
- **Alert Scorte** - Notifiche automatiche per scorte basse
- **Backup** - Salvataggio periodico inventario
- **Report** - Statistiche e analisi consumi
- **Onboarding AI** - Setup guidato dall'AI

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

## 🌐 Deploy

### Railway
1. Connetti repository GitHub
2. Configura variabili ambiente
3. Deploy automatico

### Docker
```bash
docker build -t gioia-bot .
docker run -p 8000:8000 gioia-bot
```

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