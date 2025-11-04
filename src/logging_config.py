"""
Configurazione logging colorato per telegram-ai-bot
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
    
    # Configura logger specifici per ridurre verbosità
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    
    return root_logger


