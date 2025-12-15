#!/usr/bin/env python3
"""
Script di avvio per il bot Telegram.
Esegue bot.py come script Python dalla directory corretta.
"""
import os
import sys

# Path assoluto della directory del bot
root_dir = os.path.dirname(os.path.abspath(__file__))
bot_dir = os.path.join(root_dir, "Telegram AI BOT 2")
bot_file = os.path.join(bot_dir, "bot.py")

# Verifica che la directory e il file esistano
if not os.path.exists(bot_dir):
    print(f"❌ ERRORE: Directory bot non trovata: {bot_dir}")
    print(f"   Directory corrente: {os.getcwd()}")
    print(f"   Root script: {root_dir}")
    sys.exit(1)

if not os.path.exists(bot_file):
    print(f"❌ ERRORE: File bot.py non trovato in: {bot_dir}")
    sys.exit(1)

# Cambia directory di lavoro alla directory del bot
# Questo è necessario per gli import relativi
os.chdir(bot_dir)

# Aggiungi la directory del bot al path Python
if bot_dir not in sys.path:
    sys.path.insert(0, bot_dir)

# Aggiungi la directory parent al path (per permettere import come package)
parent_dir = os.path.dirname(bot_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Esegui bot.py direttamente come script Python
# Gli import relativi funzioneranno perché:
# 1. Siamo nella directory corretta (os.chdir)
# 2. La directory ha un __init__.py (è un package)
# 3. bot.py viene eseguito come __main__
if __name__ == "__main__":
    try:
        # Leggi e esegui bot.py come script
        # Configuriamo __name__ e __package__ per permettere import relativi
        with open("bot.py", "r", encoding="utf-8") as f:
            code = f.read()
        
        # Crea un namespace con le variabili necessarie per gli import relativi
        namespace = {
            "__name__": "__main__",
            "__file__": bot_file,
            "__package__": None,  # None permette import relativi quando siamo nella directory del package
            "__path__": [bot_dir],  # Path del package
        }
        
        # Esegui il codice
        exec(compile(code, bot_file, "exec"), namespace)
            
    except KeyboardInterrupt:
        print("\n⚠️ Bot interrotto dall'utente")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERRORE durante l'avvio del bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
