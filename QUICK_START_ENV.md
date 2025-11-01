# 🚀 Quick Start - Configurazione .env per Telegram Bot

## 📝 Cosa Devi Fare

Crea un file `.env` nella cartella `telegram-ai-bot/` con questa variabile **CRITICA**:

```env
PROCESSOR_URL=http://localhost:8001
```

## 🎯 Variabili Necessarie

### **Per Test Locale:**

Crea `telegram-ai-bot/.env`:
```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_token_here

# OpenAI
OPENAI_API_KEY=your_key_here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/gioia_db

# ⭐ PROCESSOR URL (IMPORTANTE!)
PROCESSOR_URL=http://localhost:8001
```

### **Per Produzione (Railway):**

Sul Railway, nelle **Variables** del servizio bot, aggiungi:
```
PROCESSOR_URL=https://your-processor-service.railway.app
```

---

## ✅ Verifica

Quando avvii il bot, dovresti vedere nel log:
```
🔗 Processor URL: http://localhost:8001
✅ Configurazione validata con successo
```

Se vedi questo, il bot è configurato correttamente! 🎉


