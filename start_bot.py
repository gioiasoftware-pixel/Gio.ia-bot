#!/usr/bin/env python3
"""
Script di avvio per il bot Telegram.
Esegue il bot come modulo Python dalla directory corretta per gestire gli import relativi.
"""
import os
import sys
import runpy

# Path assoluto della directory del bot
root_dir = os.path.dirname(os.path.abspath(__file__))
bot_dir = os.path.join(root_dir, "Telegram AI BOT 2")

# Verifica che la directory esista
if not os.path.exists(bot_dir):
    print(f"❌ ERRORE: Directory bot non trovata: {bot_dir}")
    print(f"   Directory corrente: {os.getcwd()}")
    print(f"   Root script: {root_dir}")
    sys.exit(1)

# Cambia directory di lavoro alla directory del bot
# Questo è necessario per gli import relativi
os.chdir(bot_dir)

# Aggiungi la directory del bot al path Python
if bot_dir not in sys.path:
    sys.path.insert(0, bot_dir)

# Esegui bot come modulo Python usando runpy
# Questo permette agli import relativi (.ai, .new_onboarding, etc.) di funzionare correttamente
if __name__ == "__main__":
    try:
        # Esegui bot come modulo (equivalente a: python -m bot)
        # runpy.run_module esegue il modulo come se fosse eseguito con python -m
        runpy.run_module("bot", run_name="__main__")
    except KeyboardInterrupt:
        print("\n⚠️ Bot interrotto dall'utente")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERRORE durante l'avvio del bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
