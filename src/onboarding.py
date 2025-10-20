"""
Sistema di onboarding per nuovi utenti
"""
import logging
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .database import db_manager

logger = logging.getLogger(__name__)

class OnboardingManager:
    """Gestore del processo di onboarding"""
    
    def __init__(self):
        self.onboarding_steps = {
            'business_name': {
                'question': "🏢 Qual è il nome della tua attività?",
                'field': 'business_name'
            },
            'business_type': {
                'question': "🍷 Che tipo di attività hai?",
                'field': 'business_type',
                'keyboard': [
                    [InlineKeyboardButton("🍷 Enoteca", callback_data="type_enoteca")],
                    [InlineKeyboardButton("🍽️ Ristorante", callback_data="type_ristorante")],
                    [InlineKeyboardButton("🍸 Bar", callback_data="type_bar")],
                    [InlineKeyboardButton("🏪 Negozio", callback_data="type_negozio")],
                    [InlineKeyboardButton("🏠 Privato", callback_data="type_privato")],
                    [InlineKeyboardButton("📝 Altro", callback_data="type_altro")]
                ]
            },
            'location': {
                'question': "📍 In che città/regione ti trovi?",
                'field': 'location'
            },
            'phone': {
                'question': "📞 Qual è il tuo numero di telefono? (opzionale)",
                'field': 'phone',
                'optional': True
            },
            'email': {
                'question': "📧 Qual è la tua email? (opzionale)",
                'field': 'email',
                'optional': True
            }
        }
    
    def start_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Avvia il processo di onboarding"""
        user = update.effective_user
        telegram_id = user.id
        
        # Verifica se l'utente esiste già
        existing_user = db_manager.get_user_by_telegram_id(telegram_id)
        if not existing_user:
            # Crea nuovo utente
            db_manager.create_user(
                telegram_id=telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
        
        # Inizia con il primo step
        self._send_onboarding_step(update, context, 'business_name')
    
    def _send_onboarding_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE, step: str) -> None:
        """Invia un step dell'onboarding"""
        step_data = self.onboarding_steps[step]
        question = step_data['question']
        
        if 'keyboard' in step_data:
            # Step con tastiera inline
            keyboard = InlineKeyboardMarkup(step_data['keyboard'])
            update.message.reply_text(question, reply_markup=keyboard)
        else:
            # Step con risposta testuale
            update.message.reply_text(question)
        
        # Salva lo step corrente nel context
        context.user_data['onboarding_step'] = step
    
    def handle_onboarding_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le risposte durante l'onboarding"""
        if 'onboarding_step' not in context.user_data:
            return False
        
        current_step = context.user_data['onboarding_step']
        step_data = self.onboarding_steps[current_step]
        
        if current_step == 'business_name':
            # Salva il nome dell'attività
            business_name = update.message.text.strip()
            context.user_data['onboarding_data'] = {'business_name': business_name}
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'business_type')
            return True
        
        elif current_step == 'location':
            # Salva la localizzazione
            location = update.message.text.strip()
            context.user_data['onboarding_data']['location'] = location
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'phone')
            return True
        
        elif current_step == 'phone':
            # Salva il telefono (opzionale)
            phone = update.message.text.strip() if update.message.text.strip() else None
            context.user_data['onboarding_data']['phone'] = phone
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'email')
            return True
        
        elif current_step == 'email':
            # Salva l'email (opzionale)
            email = update.message.text.strip() if update.message.text.strip() else None
            context.user_data['onboarding_data']['email'] = email
            
            # Completa l'onboarding
            self._complete_onboarding(update, context)
            return True
        
        return False
    
    def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Gestisce le callback query durante l'onboarding"""
        query = update.callback_query
        query.answer()
        
        if 'onboarding_step' not in context.user_data:
            return False
        
        current_step = context.user_data['onboarding_step']
        
        if current_step == 'business_type':
            # Estrai il tipo di attività dalla callback
            business_type_map = {
                'type_enoteca': 'Enoteca',
                'type_ristorante': 'Ristorante',
                'type_bar': 'Bar',
                'type_negozio': 'Negozio',
                'type_privato': 'Privato',
                'type_altro': 'Altro'
            }
            
            business_type = business_type_map.get(query.data, 'Altro')
            context.user_data['onboarding_data']['business_type'] = business_type
            
            # Passa al prossimo step
            self._send_onboarding_step(update, context, 'location')
            return True
        
        return False
    
    def _complete_onboarding(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Completa il processo di onboarding"""
        user = update.effective_user
        telegram_id = user.id
        onboarding_data = context.user_data.get('onboarding_data', {})
        
        # Aggiorna il database
        success = db_manager.update_user_onboarding(
            telegram_id=telegram_id,
            onboarding_completed=True,
            **onboarding_data
        )
        
        if success:
            # Messaggio di completamento
            completion_text = (
                "🎉 **Onboarding completato con successo!**\n\n"
                f"🏢 **Attività:** {onboarding_data.get('business_name', 'N/A')}\n"
                f"🍷 **Tipo:** {onboarding_data.get('business_type', 'N/A')}\n"
                f"📍 **Località:** {onboarding_data.get('location', 'N/A')}\n"
                f"📞 **Telefono:** {onboarding_data.get('phone', 'Non fornito')}\n"
                f"📧 **Email:** {onboarding_data.get('email', 'Non fornita')}\n\n"
                "🚀 **Ora puoi iniziare a gestire il tuo inventario vini!**\n\n"
                "💡 **Comandi disponibili:**\n"
                "• `/inventario` - Vedi il tuo inventario\n"
                "• `/aggiungi` - Aggiungi un vino\n"
                "• `/report` - Genera report\n"
                "• `/help` - Guida completa"
            )
            
            update.message.reply_text(completion_text, parse_mode='Markdown')
            
            # Pulisci i dati temporanei
            context.user_data.pop('onboarding_step', None)
            context.user_data.pop('onboarding_data', None)
            
            logger.info(f"Onboarding completato per utente {telegram_id}")
        else:
            update.message.reply_text("❌ Errore durante il salvataggio. Riprova con `/start`.")
    
    def is_onboarding_complete(self, telegram_id: int) -> bool:
        """Verifica se l'onboarding è completato"""
        user = db_manager.get_user_by_telegram_id(telegram_id)
        return user and user.onboarding_completed if user else False

# Istanza globale del gestore onboarding
onboarding_manager = OnboardingManager()
