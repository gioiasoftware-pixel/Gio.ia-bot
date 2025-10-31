# 🔧 Configurazione Variabili Ambiente - Telegram Bot

## 📋 Variabili Obbligatorie

### **1. TELEGRAM_BOT_TOKEN**
Token del bot Telegram ottenuto da @BotFather
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### **2. OPENAI_API_KEY**
Chiave API OpenAI per le funzionalità AI
```
OPENAI_API_KEY=sk-...
```

### **3. DATABASE_URL**
Connection string PostgreSQL
```
DATABASE_URL=postgresql://user:password@localhost:5432/gioia_db
```

### **4. PROCESSOR_URL** ⭐ **IMPORTANTE**
**Questo è l'URL del processor a cui il bot invia i file.**

#### **Per Test Locale:**
```env
PROCESSOR_URL=http://localhost:8001
```

#### **Per Produzione (Railway):**
```env
PROCESSOR_URL=https://gioia-processor-production.railway.app
```

---

## 📝 File .env Esempio

Crea un file `.env` nella cartella `telegram-ai-bot/` con questo contenuto:

### **Versione Locale (per test):**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://user:password@localhost:5432/gioia_db

# Processor locale
PROCESSOR_URL=http://localhost:8001

BOT_MODE=polling
PORT=8000
```

### **Versione Produzione (Railway):**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://user:password@host:5432/gioia_db

# Processor Railway
PROCESSOR_URL=https://your-processor.railway.app

BOT_MODE=polling
PORT=8000
```

---

## 🧪 Verifica Configurazione

Dopo aver creato il file `.env`, puoi verificare che il bot legga correttamente `PROCESSOR_URL`:

```python
# Test rapido
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('PROCESSOR_URL:', os.getenv('PROCESSOR_URL', 'NOT SET'))"
```

---

## 🚀 Come Funziona

1. **Bot avvia** → legge `.env` → carica `PROCESSOR_URL`
2. **Bot riceve file** → scarica da Telegram → invia a `PROCESSOR_URL/process-inventory`
3. **Processor elabora** → risponde → bot mostra risultato

**Flusso:**
```
Telegram → Bot (.env → PROCESSOR_URL) → Processor → Database
```

---

## ⚠️ Note

- Se `PROCESSOR_URL` non è settato, il bot usa il default: `http://localhost:8001`
- In produzione su Railway, assicurati che `PROCESSOR_URL` punti all'URL pubblico del processor
- Il processor deve essere raggiungibile dal bot (stessa rete locale per test, pubblico per produzione)

