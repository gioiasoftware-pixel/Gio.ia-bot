# Gio.ia-bot 🤖

**Bot Telegram intelligente con AI per la gestione inventario vini**

Un assistente AI completo che gestisce inventario, movimenti, backup e report per ristoranti ed enoteche.

---

## ✨ **FUNZIONALITÀ PRINCIPALI**

### 🤖 **AI Conversazionale**
- **Chat naturale** - Risponde a qualsiasi messaggio
- **Contesto intelligente** - Conosce il tuo inventario e movimenti
- **Consigli personalizzati** - Suggerimenti basati sui tuoi dati

### 📋 **Onboarding Completo**
- **Upload inventario** - CSV, Excel o foto con OCR
- **Configurazione profilo** - Nome utente e locale
- **Backup automatico** - Inventario iniziale salvato

### 📦 **Gestione Inventario**
- **Movimenti automatici** - Riconosce consumi e rifornimenti
- **Log completo** - Storico di tutti i movimenti
- **Alert scorte basse** - Notifiche automatiche
- **Backup periodici** - Sicurezza dei dati

### 📊 **Report e Analisi**
- **Report giornalieri** - Riassunto movimenti
- **Statistiche vendite** - Top vini venduti
- **Analisi consumi** - Trend e pattern
- **Export dati** - Per analisi esterne

---

## 🚀 **INSTALLAZIONE RAPIDA**

### **1. Clona il repository**
```bash
git clone https://github.com/gioiasoftware-pixel/Gio.ia-bot.git
cd Gio.ia-bot
```

### **2. Configura ambiente**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### **3. Configura variabili**
Modifica `.env` con i tuoi token:
```env
TELEGRAM_BOT_TOKEN=il_tuo_token_telegram
OPENAI_API_KEY=la_tua_chiave_openai
```

### **4. Avvia il bot**
```bash
python -m src.bot
```

---

## 🎯 **COME USARE IL BOT**

### **Primo Avvio**
1. Scrivi `/start` al bot
2. Carica il tuo inventario (CSV/Excel/Foto)
3. Inserisci nome utente e locale
4. Il sistema crea backup automatico

### **Gestione Quotidiana**
**Comunica movimenti naturalmente:**
- "Ho venduto 2 bottiglie di Chianti"
- "Ho ricevuto 10 bottiglie di Barolo"
- "Ho consumato 1 Prosecco"

**Chiedi informazioni:**
- "Come va l'inventario?"
- "Quali vini devo riordinare?"
- "Fammi un report delle vendite"

### **Comandi Disponibili**
- `/start` - Avvia o mostra profilo
- `/help` - Guida completa
- `/inventario` - Visualizza inventario
- `/log` - Mostra movimenti
- `/scorte` - Alert scorte basse
- `/aggiungi` - Aggiungi nuovo vino
- `/upload` - Carica file inventario

---

## 🏗️ **ARCHITETTURA TECNICA**

### **Stack Tecnologico**
- **Python 3.12** - Linguaggio principale
- **python-telegram-bot** - API Telegram
- **OpenAI GPT-4o-mini** - AI conversazionale
- **PostgreSQL** - Database persistente
- **SQLAlchemy** - ORM database
- **Railway.app** - Hosting e deploy

### **Struttura Database**
```sql
users              -- Dati utenti
├── wines          -- Inventario vini
├── inventory_backups -- Backup inventario
└── inventory_logs    -- Log movimenti
```

### **Moduli Principali**
- `bot.py` - Handler Telegram e routing
- `ai.py` - Integrazione OpenAI con contesto
- `database.py` - Gestione PostgreSQL
- `new_onboarding.py` - Flusso registrazione
- `inventory_movements.py` - Gestione movimenti
- `file_upload.py` - Upload e OCR

---

## 🚀 **DEPLOY SU RAILWAY**

### **Setup Automatico**
1. **Connetti GitHub** a Railway
2. **Aggiungi PostgreSQL** service
3. **Configura variabili ambiente:**
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `DATABASE_URL` (automatico)

### **Deploy**
```bash
git push origin main
```
Railway fa deploy automatico!

---

## 💰 **COSTI OPERATIVI**

### **OpenAI API**
- **Costo per messaggio:** ~$0.0001
- **100 messaggi/giorno:** ~$0.30/mese
- **1000 messaggi/giorno:** ~$3.00/mese

### **Railway**
- **Piano gratuito:** 500 ore/mese
- **PostgreSQL:** Incluso nel piano

---

## 🔧 **SVILUPPO**

### **Struttura Progetto**
```
src/
├── bot.py              # Handler principale
├── ai.py               # Integrazione OpenAI
├── database.py         # Modelli e gestione DB
├── new_onboarding.py   # Flusso registrazione
├── inventory_movements.py # Gestione movimenti
├── file_upload.py      # Upload e OCR
├── inventory.py        # Gestione inventario
└── config.py           # Configurazione
```

### **Aggiungere Funzionalità**
1. **Crea nuovo modulo** in `src/`
2. **Aggiungi handler** in `bot.py`
3. **Testa localmente**
4. **Deploy su Railway**

---

## 📱 **ESEMPI CONVERSAZIONE**

### **Onboarding**
```
Utente: /start
Bot: 📤 Benvenuto! Carica il tuo inventario iniziale...

Utente: [carica file CSV]
Bot: ✅ File caricato! 45 vini estratti. Nome utente?

Utente: Mario
Bot: 👤 Perfetto Mario! Nome del locale?

Utente: Ristorante da Mario
Bot: 🎉 Onboarding completato! Sistema pronto!
```

### **Gestione Movimenti**
```
Utente: Ho venduto 2 bottiglie di Chianti
Bot: ✅ Consumo registrato
     🍷 Chianti - 15 → 13 bottiglie
     📉 Consumate: 2 bottiglie

Utente: Come va l'inventario?
Bot: 📊 Inventario: 45 vini, 120 bottiglie totali
     ⚠️ 3 vini con scorte basse
     📈 Vendite oggi: 8 bottiglie
```

---

## 🆘 **SUPPORTO**

### **Problemi Comuni**
- **Bot non risponde:** Verifica token Telegram
- **Errore AI:** Controlla credito OpenAI
- **Database error:** Verifica connessione PostgreSQL

### **Log e Debug**
- **Railway logs:** Dashboard → Deployments → Logs
- **Errori AI:** Logs mostrano errore specifico
- **Database:** Verifica `DATABASE_URL`

---

## 📄 **LICENZA**

MIT License - Vedi file `LICENSE` per dettagli.

---

## 🤝 **CONTRIBUTI**

1. Fork del repository
2. Crea feature branch
3. Commit delle modifiche
4. Push al branch
5. Apri Pull Request

---

**Sviluppato con ❤️ per la gestione intelligente dell'inventario vini**