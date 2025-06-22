import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import random
import string
from uuid import uuid4

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранение данных
users = {}  # {anon_id: {"tg_id": tg_id, "contacts": [other_anon_ids]}}
pending_messages = {}  # {receiver_anon_id: [{"sender": sender_anon_id, "text": text}]}

def generate_anon_id():
    return str(uuid4())

def start(update: Update, context: CallbackContext) -> None:
    tg_user = update.effective_user
    anon_id = None
    
    # Проверяем, есть ли уже пользователь
    for uid, data in users.items():
        if data["tg_id"] == tg_user.id:
            anon_id = uid
            break
    
    # Если нет - создаем нового
    if not anon_id:
        anon_id = generate_anon_id()
        users[anon_id] = {
            "tg_id": tg_user.id,
            "contacts": []
        }
    
    keyboard = [
        [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
        [InlineKeyboardButton("Написать новому контакту", callback_data='new_contact')],
        [InlineKeyboardButton("Мой анонимный ID", callback_data='show_id')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f'👋 Добро пожаловать в анонимный мессенджер!\n'
        f'Ваш ID: {anon_id}\n'
        f'Вы можете поделиться этим ID с другими, чтобы они могли добавить вас в контакты.',
        reply_markup=reply_markup
    )

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
            query.edit_message_text("У вас пока нет контактов.")
        else:
            contacts_list = "\n".join(users[anon_id]["contacts"])
            keyboard = [
                [InlineKeyboardButton(f"Написать {contact}", callback_data=f'write_{contact}')] 
                for contact in users[anon_id]["contacts"]
            ]
            keyboard.append([InlineKeyboardButton("Назад", callback_data='back_to_main')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text(f"Ваши контакты:\n{contacts_list}", reply_markup=reply_markup)
    
    elif query.data == 'new_contact':
        context.user_data["awaiting_contact_id"] = True
        query.edit_message_text("Введите анонимный ID контакта, которого хотите добавить:")
    
    elif query.data == 'show_id':
        keyboard = [
            [InlineKeyboardButton("Назад", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(f"Ваш анонимный ID:\n{anon_id}", reply_markup=reply_markup)
    
    elif query.data == 'back_to_main':
        keyboard = [
            [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
            [InlineKeyboardButton("Написать новому контакту", callback_data='new_contact')],
            [InlineKeyboardButton("Мой анонимный ID", callback_data='show_id')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("Главное меню:", reply_markup=reply_markup)
    
    elif query.data.startswith('write_'):
        contact_id = query.data[6:]
        context.user_data["current_contact"] = contact_id
        query.edit_message_text(f"Вы пишете {contact_id}. Введите сообщение:")

def handle_message(update: Update, context: CallbackContext) -> None:
    tg_user = update.effective_user
    message_text = update.message.text
    
    # Находим anon_id пользователя
    anon_id = None
    for uid, data in users.items():
        if data["tg_id"] == tg_user.id:
            anon_id = uid
            break
    
    if not anon_id:
        update.message.reply_text("Ошибка: пользователь не найден")
        return
    
    # Если ожидается ввод ID нового контакта
    if context.user_data.get("awaiting_contact_id"):
        contact_id = message_text.strip()
        if contact_id in users:
            if contact_id not in users[anon_id]["contacts"]:
                users[anon_id]["contacts"].append(contact_id)
                update.message.reply_text(f"Контакт {contact_id} успешно добавлен!")
            else:
                update.message.reply_text("Этот контакт уже есть в вашем списке.")
        else:
            update.message.reply_text("Контакт с таким ID не найден.")
        context.user_data["awaiting_contact_id"] = False
        return
    
    # Если идет переписка с контактом
    if "current_contact" in context.user_data:
        contact_id = context.user_data["current_contact"]
        if contact_id not in users:
            update.message.reply_text("Ошибка: контакт не найден")
            return
        
        # Сохраняем сообщение для получателя
        if contact_id not in pending_messages:
            pending_messages[contact_id] = []
        
        pending_messages[contact_id].append({
            "sender": anon_id,
            "text": message_text
        })
        
        update.message.reply_text("Сообщение отправлено!")
        
        # Уведомляем получателя, если он активен
        receiver_tg_id = users[contact_id]["tg_id"]
        context.bot.send_message(
            receiver_tg_id,
            f"У вас новое сообщение от {anon_id}! Нажмите 'Мои контакты' чтобы прочитать."
        )
        
        context.user_data.pop("current_contact", None)
        return
    
    # Проверяем входящие сообщения
    if anon_id in pending_messages and pending_messages[anon_id]:
        for msg in pending_messages[anon_id]:
            update.message.reply_text(f"Сообщение от {msg['sender']}:\n{msg['text']}")
        pending_messages[anon_id] = []

def main() -> None:
    # Замените 'YOUR_TOKEN' на токен вашего бота
    updater = Updater("7551307559:AAFILG2qOVlvCvmkyRGToGs8XFCT9p3mnok")
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()