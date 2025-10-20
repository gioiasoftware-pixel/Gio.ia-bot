import asyncio
import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from .config import TELEGRAM_BOT_TOKEN, BOT_MODE, WEBHOOK_URL, PORT, validate_config
from .ai import get_ai_response
from aiohttp import web

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao! Sono Gio.ia-bot 🤖\n"
        "Il tuo assistente AI per la gestione inventario!\n"
        "Scrivimi qualcosa o chiedi /help per iniziare."
    )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra i comandi disponibili."""
    help_text = (
        "🤖 **Gio.ia-bot - Comandi disponibili:**\n\n"
        "📋 **Comandi base:**\n"
        "/start - Avvia il bot\n"
        "/help - Mostra questo messaggio\n\n"
        "💬 **Chat:**\n"
        "Scrivi qualsiasi messaggio per chattare con l'AI!\n\n"
        "🔧 **Funzionalità:**\n"
        "• Gestione inventario\n"
        "• Report e statistiche\n"
        "• Assistenza AI specializzata\n\n"
        "❓ **Hai bisogno di aiuto?**\n"
        "Scrivi semplicemente la tua domanda!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i messaggi di chat con l'AI."""
    try:
        user_text = update.message.text
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        logger.info(f"Messaggio ricevuto da {username} (ID: {user_id}): {user_text[:50]}...")
        
        await update.message.reply_text("💭 Sto pensando...")
        reply = get_ai_response(user_text)
        
        await update.message.reply_text(reply)
        logger.info(f"Risposta inviata a {username}")
        
    except Exception as e:
        logger.error(f"Errore in chat handler: {e}")
        await update.message.reply_text("⚠️ Errore temporaneo. Riprova tra qualche minuto.")


async def healthcheck_handler(request: web.Request):
    """Endpoint HTTP per l'healthcheck di Railway"""
    logger.info("Healthcheck richiesto")
    return web.Response(text="OK", status=200)




async def _run_health_only_server(port: int) -> None:
    """Avvia solo il server per l'healthcheck, utile quando il WEBHOOK_URL manca.
    Mantiene il processo vivo per permettere a Railway di passare l'healthcheck.
    """
    web_app = web.Application()
    web_app.router.add_get('/health', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🩺 Server healthcheck in ascolto su porta {port}")
    # Mantiene il processo vivo
    await asyncio.Event().wait()


def main():
    """Funzione principale per avviare il bot."""
    try:
        # Valida configurazione all'avvio
        validate_config()
        
        logger.info("🚀 Avvio Gio.ia-bot...")
        
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
        
        # Controlla se siamo su Railway (webhook) o locale (polling)
        if BOT_MODE == "webhook" or os.getenv("RAILWAY_ENVIRONMENT"):
            # Modalità webhook per Railway
            logger.info(f"🌐 Modalità webhook - Porta: {PORT}")
            
            if not WEBHOOK_URL:
                logger.warning("⚠️ WEBHOOK_URL non configurata! Avvio solo endpoint /health...")
                asyncio.run(_run_health_only_server(PORT))
                return
                
            # Nasconde il token nei log per sicurezza
            webhook_display = WEBHOOK_URL.replace(WEBHOOK_URL.split('/')[-1], "***") if WEBHOOK_URL else "Non configurata"
            logger.info(f"📡 Webhook URL: {webhook_display}")
            
            # Crea server aiohttp con endpoint healthcheck
            web_app = web.Application()
            web_app.router.add_get("/healthcheck", healthcheck_handler)
            
            # Avvia il server web per i webhook con aiohttp integrato
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                webhook_url=WEBHOOK_URL,
                webhook_path="/webhook",
                web_app=web_app
            )
        else:
            # Modalità polling per sviluppo locale
            logger.info("✅ Bot avviato in modalità polling. Premi Ctrl+C per fermarlo.")
            app.run_polling()
            
    except ValueError as e:
        logger.error(f"❌ Errore di configurazione: {e}")
        print(f"\n{e}\n")
        print("💡 Crea un file .env basato su .env.example e configura le variabili richieste.")
        return
    except Exception as e:
        logger.error(f"❌ Errore critico all'avvio: {e}")
        print(f"❌ Errore critico: {e}")
        return


if __name__ == "__main__":
    # "main" non è una coroutine; chiamarlo direttamente evita errori e garantisce l'avvio corretto
    main()



