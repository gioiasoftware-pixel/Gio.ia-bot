# Feature: Messaggi Audio (Speech-to-Text)

## 📋 Stato
**Status**: Planned (da implementare in seguito)  
**Priorità**: Media  
**Stima**: 2-3 ore di sviluppo

## 🎯 Obiettivo
Permettere agli utenti di inviare messaggi vocali (voice notes, audio files) che vengono automaticamente trascritti e processati come messaggi testuali.

## 🔧 Implementazione Tecnica

### Componenti da Aggiungere

1. **Nuovi Handler Bot** (`src/bot.py`)
   - `MessageHandler(filters.VOICE, handle_voice)`
   - `MessageHandler(filters.AUDIO, handle_audio)`
   - `MessageHandler(filters.VIDEO_NOTE, handle_video_note)` (opzionale)

2. **Trascrittore Audio** (`src/audio_transcriber.py` - nuovo file)
   - Metodo: OpenAI Whisper API (prima scelta)
   - Fallback: whisper.cpp locale o Vosk
   - Conversione ffmpeg se necessario (OGG/Opus → WAV 16k mono)
   - Gestione timeout e chunking per audio lunghi

3. **Utility Conversione** (`src/audio_utils.py` - nuovo file, opzionale)
   - Wrapper ffmpeg per normalizzare formati
   - Validazione dimensione/durata

### Flusso Operativo

```
1. Utente invia audio → Bot riceve file_id
2. Download file via Bot API → bytes
3. Conversione formati (se necessario) → WAV/MP3
4. Invio a Whisper API → trascrizione testo
5. Salvataggio trascrizione in LOG interazione (role='user')
6. Processamento come messaggio testo normale → get_ai_response()
7. Risposta all'utente + salvataggio in LOG (role='assistant')
```

### Features UX

- Messaggio intermedio: "🎙️ Ricevuto audio, trascrivo..."
- Bottone "✏️ Modifica testo" se confidence bassa
- Cache trascrizioni per `file_id` (evita re-trascrizione su retry)
- Rate limiting audio (es. 3 audio/minuto per utente)
- Comando `/audio off` per disabilitare feature per utente

### Configurazione ENV

```env
AUDIO_TRANSCRIBER=whisper_api|whisper_local|vosk
OPENAI_API_KEY=<già presente>
AUDIO_MAX_SECONDS=120
AUDIO_MAX_SIZE_MB=25
FFMPEG_PATH=/usr/bin/ffmpeg  # Se conversione locale
```

### Dipendenze Nuove

```txt
openai>=2.0.0  # Già presente per Whisper API
ffmpeg-python>=0.2.0  # Opzionale, solo se conversione locale
```

### Note Implementazione

- ✅ Tutto asincrono (già architettura bot)
- ✅ Riutilizzo LOG interazione esistente
- ✅ Nessuna nuova tabella DB necessaria
- ✅ Trascrizione → testo → pipeline esistente AI
- ⚠️ Costi Whisper API: ~€0.006 per minuto (valutare limiti)
- ⚠️ CPU: se uso whisper locale, valutare worker separato

## 📝 TODO Implementazione

- [ ] Creare `src/audio_transcriber.py` con wrapper Whisper API
- [ ] Aggiungere handler VOICE/AUDIO in `src/bot.py`
- [ ] Integrare trascrizione nel flusso chat_handler esistente
- [ ] Aggiungere cache trascrizioni (tabella o Redis opzionale)
- [ ] Template messaggi feedback utente ("🎙️ Trascrivo...")
- [ ] Rate limiter specifico per audio
- [ ] Comando `/audio off/on` per toggle feature
- [ ] Testing con vari formati audio (OGG, MP3, WAV)
- [ ] Documentazione feature per utenti finali

## 🔗 Riferimenti

- [Telegram Bot API - Voice Messages](https://core.telegram.org/bots/api#voice)
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
- [Python Telegram Bot - Filters](https://python-telegram-bot.readthedocs.io/en/stable/telegram.ext.filters.html)


