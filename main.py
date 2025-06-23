import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from uuid import uuid4

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

users = {}
pending_messages = {}

def generate_anon_id():
    return str(uuid4())

def start(update: Update, context: CallbackContext) -> None:
    tg_user = update.effective_user
    anon_id = None
    
    for uid, data in users.items():
        if data["tg_id"] == tg_user.id:
            anon_id = uid
            break
    
    if not anon_id:
        anon_id = generate_anon_id()
        users[anon_id] = {
            "tg_id": tg_user.id,
            "contacts": []
        }
    
    keyboard = [
        [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
        [InlineKeyboardButton("Написать новому контакту", callback_data='new_contact')],
        [InlineKeyboardButton("Мой анонимный ID", callback_data='show_id')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f'👋 Добро пожаловать!\nВаш ID: {anon_id}\nИспользуйте /help для справки',
        reply_markup=reply_markup
    )

def help_command(update: Update, context: CallbackContext) -> None:
    help_text = """
📚 Помощь по боту:

Это анонимный мессенджер. Ваш ID создается автоматически.

Основные команды:
/start - Начать работу
/help - Справка

Как писать:
1. Добавьте контакт по ID
2. Выберите контакт
3. Отправьте сообщение
"""
    update.message.reply_text(help_text)

def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    tg_user = query.from_user
    anon_id = None
    
    for uid, data in users.items():
        if data["tg_id"] == tg_user.id:
            anon_id = uid
            break
    
    if not anon_id:
        query.edit_message_text("Ошибка: пользователь не найден")
        return
    
    if query.data == 'contacts':
        if not users[anon_id]["contacts"]:
            query.edit_message_text("Контактов нет")
        else:
            contacts_list = "\n".join(users[anon_id]["contacts"])
            keyboard = [
                [InlineKeyboardButton(f"Написать {contact}", callback_data=f'write_{contact}')] 
                for contact in users[anon_id]["contacts"]
            ]
            keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_main')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(f"Контакты:\n{contacts_list}", reply_markup=reply_markup)
    
    elif query.data == 'new_contact':
        context.user_data["awaiting_contact_id"] = True
        query.edit_message_text("Введите ID контакта:")
    
    elif query.data == 'show_id':
        keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(f"Ваш ID:\n{anon_id}", reply_markup=reply_markup)
    
    elif query.data == 'back_to_main':
        show_main_menu(query)
    
    elif query.data == 'help':
        help_command(update, context)
        query.message.delete()
    
    elif query.data.startswith('write_'):
        contact_id = query.data[6:]
        if contact_id not in users[anon_id]["contacts"]:
            query.edit_message_text("Контакт не найден")
            return
        context.user_data["current_contact"] = contact_id
        query.edit_message_text(f"Пишите {contact_id}:")

def show_main_menu(query):
    keyboard = [
        [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
        [InlineKeyboardButton("Написать новому контакту", callback_data='new_contact')],
        [InlineKeyboardButton("Мой анонимный ID", callback_data='show_id')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text("Главное меню:", reply_markup=reply_markup)

def handle_message(update: Update, context: CallbackContext) -> None:
    tg_user = update.effective_user
    message_text = update.message.text
    
    anon_id = None
    for uid, data in users.items():
        if data["tg_id"] == tg_user.id:
            anon_id = uid
            break
    
    if not anon_id:
        update.message.reply_text("Ошибка: пользователь не найден")
        return
    
    if context.user_data.get("awaiting_contact_id"):
        contact_id = message_text.strip()
        
        if contact_id == anon_id:
            update.message.reply_text("Нельзя добавить себя!")
            context.user_data["awaiting_contact_id"] = False
            return
        
        if contact_id in users:
            if contact_id not in users[anon_id]["contacts"]:
                users[anon_id]["contacts"].append(contact_id)
                update.message.reply_text(f"Контакт {contact_id} добавлен!")
            else:
                update.message.reply_text("Контакт уже есть")
        else:
            update.message.reply_text("Контакт не найден")
        
        context.user_data["awaiting_contact_id"] = False
        return
    
    if "current_contact" in context.user_data:
        contact_id = context.user_data["current_contact"]
        
        if contact_id not in users:
            update.message.reply_text("Контакт не найден")
            context.user_data.pop("current_contact", None)
            return
        
        if len(message_text) > 4000:
            update.message.reply_text("Слишком длинное сообщение")
            return
        
        if contact_id not in pending_messages:
            pending_messages[contact_id] = []
        
        pending_messages[contact_id].append({
            "sender": anon_id,
            "text": message_text
        })
        
        update.message.reply_text("Сообщение отправлено!")
        
        receiver_tg_id = users[contact_id]["tg_id"]
        try:
            context.bot.send_message(
                receiver_tg_id,
                f"Новое сообщение от {anon_id}!"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
        
        context.user_data.pop("current_contact", None)
        return
    
    if anon_id in pending_messages and pending_messages[anon_id]:
        for msg in pending_messages[anon_id]:
            update.message.reply_text(f"Сообщение от {msg['sender']}:\n{msg['text']}")
        pending_messages[anon_id] = []

def main() -> None:
    # Вставьте сюда токен вашего бота
    updater = Updater("ВАШ_ТОКЕН_БОТА", use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    logger.info("Бот запущен")
    updater.idle()

if __name__ == '__main__':
    main()