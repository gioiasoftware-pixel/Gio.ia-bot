import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from .config import TELEGRAM_BOT_TOKEN, BOT_MODE
from .ai import get_ai_response
from aiohttp import web


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao! Sono Gio.ia-bot 🤖\n"
        "Il tuo assistente AI per la gestione inventario!\n"
        "Scrivimi qualcosa o chiedi /help per iniziare."
    )


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comandi disponibili:\n/start - avvia\n/help - aiuto")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("💭 Sto pensando...")
    reply = get_ai_response(user_text)
    await update.message.reply_text(reply)


async def health_check(request):
    """Endpoint per l'healthcheck di Railway"""
    return web.Response(text="OK", status=200)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    
    # Controlla se siamo su Railway (webhook) o locale (polling)
    if BOT_MODE == "webhook" or os.getenv("RAILWAY_ENVIRONMENT"):
        # Modalità webhook per Railway
        port = int(os.getenv("PORT", 8000))
        webhook_url = os.getenv("WEBHOOK_URL")
        
        if not webhook_url:
            print("⚠️ WEBHOOK_URL non configurata!")
            return
            
        print(f"🚀 Bot avviato in modalità webhook su porta {port}")
        print(f"📡 Webhook URL: {webhook_url}")
        
        # Crea server web per healthcheck
        web_app = web.Application()
        web_app.router.add_get('/health', health_check)
        
        # Avvia il server web per i webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            web_app=web_app
        )
    else:
        # Modalità polling per sviluppo locale
        print("✅ Bot avviato in modalità polling. Premi Ctrl+C per fermarlo.")
        app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())



