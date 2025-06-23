from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from uuid import uuid4
import logging
from datetime import datetime, timedelta

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Хранение данных
users = {}  # {anon_id: {"tg_id": tg_id, "contacts": [other_anon_ids]}}
pending_messages = {}  # {receiver_anon_id: [{"sender": sender_anon_id, "text": text, "timestamp": datetime}]}

def generate_anon_id():
    return str(uuid4())

def cleanup_old_messages():
    """Удаляем сообщения старше 30 дней"""
    global pending_messages
    cutoff = datetime.now() - timedelta(days=30)
    for receiver in list(pending_messages.keys()):
        pending_messages[receiver] = [
            msg for msg in pending_messages[receiver] 
            if msg['timestamp'] > cutoff
        ]
        if not pending_messages[receiver]:
            del pending_messages[receiver]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    anon_id = next((uid for uid, data in users.items() if data["tg_id"] == user.id), None)
    
    if not anon_id:
        anon_id = generate_anon_id()
        users[anon_id] = {"tg_id": user.id, "contacts": []}
    
    # Проверяем входящие сообщения при каждом старте
    cleanup_old_messages()
    if pending_messages.get(anon_id):
        for msg in pending_messages[anon_id]:
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"📩 Новое сообщение от {msg['sender']}:\n\n{msg['text']}\n\n"
                         f"🕒 {msg['timestamp'].strftime('%d.%m.%Y %H:%M')}"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения: {e}")
        pending_messages[anon_id] = []
    
    keyboard = [
        [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
        [InlineKeyboardButton("Написать контакту", callback_data='new_contact')],
        [InlineKeyboardButton("Мой ID", callback_data='show_id')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    
    await update.message.reply_text(
        f'👋 Ваш анонимный ID: `{anon_id}`\n'
        'Используйте кнопки ниже или /help',
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 *Помощь по боту*

*Как отправлять сообщения:*
1. Нажмите "Написать контакту"
2. Введите ID получателя
3. Напишите сообщение

*Как читать сообщения:*
- Новые сообщения приходят автоматически при запуске (/start)
- Или просто отправьте любое сообщение боту

*Ваши контакты:*
- Это список ID пользователей, которым вы можете писать
- Добавляйте контакты через кнопку "Написать контакту"

⚠️ *Важно:*
- Сообщения хранятся только 30 дней
- Не передавайте свой ID посторонним
- Бот не хранит историю переписки
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    anon_id = next((uid for uid, data in users.items() if data["tg_id"] == user.id), None)
    
    if not anon_id:
        await query.edit_message_text("❌ Ошибка: сессия устарела. Нажмите /start")
        return
    
    if query.data == 'contacts':
        if not users[anon_id]["contacts"]:
            await query.edit_message_text("📭 У вас пока нет контактов")
        else:
            keyboard = [
                [InlineKeyboardButton(f"💌 Написать {contact[:8]}...", callback_data=f'write_{contact}')] 
                for contact in users[anon_id]["contacts"]
            ]
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')])
            await query.edit_message_text(
                "📒 Ваши контакты:",
                reply_markup=InlineKeyboardMarkup(keyboard)
    
    elif query.data == 'new_contact':
        context.user_data["awaiting_contact_id"] = True
        await query.edit_message_text("✏️ Введите ID контакта (полностью или первые 8 символов):")
    
    elif query.data == 'show_id':
        await query.edit_message_text(f"🔑 Ваш ID:\n`{anon_id}`", parse_mode='Markdown')
    
    elif query.data == 'help':
        await help_command(update, context)
        return
    
    elif query.data == 'back_to_main':
        keyboard = [
            [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
            [InlineKeyboardButton("Написать контакту", callback_data='new_contact')],
            [InlineKeyboardButton("Мой ID", callback_data='show_id')],
            [InlineKeyboardButton("Помощь", callback_data='help')]
        ]
        await query.edit_message_text(
            "📱 Главное меню:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith('write_'):
        contact_id = query.data[6:]
        # Ищем полный ID по первым символам
        full_contact_id = next((uid for uid in users[anon_id]["contacts"] if uid.startswith(contact_id)), None)
        if not full_contact_id:
            await query.edit_message_text("❌ Контакт не найден")
            return
        context.user_data["current_contact"] = full_contact_id
        await query.edit_message_text(f"✉️ Пишите сообщение для {full_contact_id[:8]}...:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    # Находим anon_id отправителя
    anon_id = next((uid for uid, data in users.items() if data["tg_id"] == user.id), None)
    
    if not anon_id:
        await update.message.reply_text("❌ Сессия устарела. Нажмите /start")
        return
    
    # Проверяем входящие сообщения при ЛЮБОМ текстовом сообщении
    cleanup_old_messages()
    if pending_messages.get(anon_id):
        for msg in pending_messages[anon_id]:
            try:
                await update.message.reply_text(
                    f"📩 Сообщение от {msg['sender']}:\n\n{msg['text']}\n\n"
                    f"🕒 {msg['timestamp'].strftime('%d.%m.%Y %H:%M')}"
                )
            except Exception as e:
                logger.error(f"Ошибка показа сообщения: {e}")
        pending_messages[anon_id] = []
        return
    
    # Если это ID нового контакта
    if context.user_data.get("awaiting_contact_id"):
        contact_id = message_text.strip()
        
        if contact_id == anon_id:
            await update.message.reply_text("🚫 Нельзя добавить самого себя!")
        else:
            # Ищем пользователя по полному или частичному ID
            found_user = next((uid for uid in users if uid.startswith(contact_id)), None)
            if found_user:
                if found_user not in users[anon_id]["contacts"]:
                    users[anon_id]["contacts"].append(found_user)
                    await update.message.reply_text(f"✅ Контакт {found_user[:8]}... добавлен!")
                else:
                    await update.message.reply_text("ℹ️ Этот контакт уже есть в вашем списке")
            else:
                await update.message.reply_text("❌ Пользователь с таким ID не найден")
        
        context.user_data["awaiting_contact_id"] = False
        return
    
    # Если это сообщение контакту
    if "current_contact" in context.user_data:
        contact_id = context.user_data["current_contact"]
        
        if contact_id not in users:
            await update.message.reply_text("❌ Контакт не найден")
            context.user_data.pop("current_contact", None)
            return
        
        if len(message_text) > 4000:
            await update.message.reply_text("❌ Слишком длинное сообщение (макс. 4000 символов)")
            return
        
        # Сохраняем сообщение
        if contact_id not in pending_messages:
            pending_messages[contact_id] = []
        
        pending_messages[contact_id].append({
            "sender": anon_id,
            "text": message_text,
            "timestamp": datetime.now()
        })
        
        # Уведомляем получателя
        try:
            await context.bot.send_message(
                chat_id=users[contact_id]["tg_id"],
                text=f"🔔 У вас новое сообщение от {anon_id[:8]}...!\nОтправьте любое сообщение боту чтобы прочитать."
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")
        
        await update.message.reply_text("✅ Сообщение доставлено!")
        context.user_data.pop("current_contact", None)
        return
    
    # Если просто текст без контекста
    keyboard = [
        [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
        [InlineKeyboardButton("Написать контакту", callback_data='new_contact')],
        [InlineKeyboardButton("Мой ID", callback_data='show_id')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    await update.message.reply_text(
        "ℹ️ Используйте кнопки меню или /help",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def main():
    # Замените 'ВАШ_ТОКЕН_БОТА' на реальный токен вашего бота
    application = ApplicationBuilder().token("ВАШ_ТОКЕН_БОТА").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()