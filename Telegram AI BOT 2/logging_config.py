"""
Configurazione logging colorato per Telegram AI Bot
"""
import logging
import colorlog
import sys


def setup_colored_logging(service_name: str = "telegram-bot"):
    """
    Configura logging colorato con:
    - ROSSO per ERROR
    - BLU per INFO/SUCCESS  
    - GIALLO per WARNING
    - Normale per DEBUG
    """
    # Handler per stdout con colori
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    
    # Formatter colorato
    formatter = colorlog.ColoredFormatter(
        f'%(log_color)s[%(levelname)s]%(reset)s %(cyan)s{service_name}%(reset)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG': 'white',
            'INFO': 'blue',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    
    handler.setFormatter(formatter)
    
    # Configura root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Rimuovi handler esistenti
    root_logger.handlers = []
    
    # Aggiungi handler colorato
    root_logger.addHandler(handler)
    
    # Configura logger specifici per ridurre verbosità e usare il nostro handler
    for logger_name in ('httpx', 'httpcore', 'aiohttp', 'telegram', 'telegram.ext', 'telegram.ext.Application'):
        lib_logger = logging.getLogger(logger_name)
        lib_logger.handlers = []  # Rimuovi handler esistenti
        lib_logger.addHandler(handler)  # Usa il nostro handler colorato
        lib_logger.setLevel(logging.WARNING)  # Riduci verbosità
        lib_logger.propagate = False  # Non propagare al root per evitare duplicazioni
    
    return root_logger

