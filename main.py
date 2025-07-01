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

# Конфигурация
ADMIN_IDS = [123456789]  # Замените на реальные ID администраторов
MESSAGE_RETENTION_DAYS = 30

# Хранение данных
users = {}
pending_messages = {}
all_messages = []  # Для хранения всей переписки для админа

def generate_anon_id():
    return str(uuid4())

def cleanup_old_messages():
    global pending_messages, all_messages
    cutoff = datetime.now() - timedelta(days=MESSAGE_RETENTION_DAYS)
    
    # Очистка pending_messages
    for receiver in list(pending_messages.keys()):
        pending_messages[receiver] = [
            msg for msg in pending_messages[receiver]
            if msg['timestamp'] > cutoff
        ]
        if not pending_messages[receiver]:
            del pending_messages[receiver]
    
    # Очистка all_messages
    all_messages = [msg for msg in all_messages if msg['timestamp'] > cutoff]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    anon_id = next((uid for uid, data in users.items() if data["tg_id"] == user.id), None)
    
    if not anon_id:
        anon_id = generate_anon_id()
        users[anon_id] = {"tg_id": user.id, "contacts": []}
    
    cleanup_old_messages()
    if pending_messages.get(anon_id):
        for msg in pending_messages[anon_id]:
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"📩 Новое сообщение от анонима:\n\n{msg['text']}\n\n"
                         f"🕒 {msg['timestamp'].strftime('%d.%m.%Y %H:%M')}"
                )
                # Запись в историю для админа
                all_messages.append({
                    "sender": msg['sender'],
                    "receiver": anon_id,
                    "text": msg['text'],
                    "timestamp": msg['timestamp']
                })
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

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in ADMIN_IDS:
        await admin_menu(update, context)
    else:
        await update.message.reply_text("⛔ У вас нет прав доступа к этой команде")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Просмотреть переписку", callback_data='admin_view_chat')],
        [InlineKeyboardButton("Поиск по ID", callback_data='admin_search_id')],
        [InlineKeyboardButton("Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("Выйти из админки", callback_data='admin_exit')]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "👑 Админ-панель:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "👑 Админ-панель:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_view_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_mode"] = "view_chat"
    await query.edit_message_text(
        "Введите ID пользователя для просмотра его переписки:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='admin_back')]])
    )

async def admin_search_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["admin_mode"] = "search_id"
    await query.edit_message_text(
        "Введите часть ID или Telegram ID для поиска:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='admin_back')]])
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    stats_text = f"""
📊 Статистика:
- Всего пользователей: {len(users)}
- Недоставленных сообщений: {sum(len(msgs) for msgs in pending_messages.values())}
- Всего сообщений в истории: {len(all_messages)}
"""
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='admin_back')]])
    )

async def admin_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("admin_mode", None)
    await query.edit_message_text(
        "Вы вышли из админ-панели",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Вернуться в меню", callback_data='start_menu')]])
    )

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    
    text = update.message.text
    mode = context.user_data.get("admin_mode")
    
    if mode == "view_chat":
        user_id = text.strip()
        messages = [msg for msg in all_messages if msg['sender'] == user_id or msg['receiver'] == user_id]
        
        if not messages:
            await update.message.reply_text(f"Переписка для ID {user_id} не найдена")
            return
        
        messages_sorted = sorted(messages, key=lambda x: x['timestamp'])
        response = [f"📖 Переписка для ID {user_id}:\n"]
        
        for msg in messages_sorted[-10:]:
            direction = "➡️ Отправлено" if msg['sender'] == user_id else "⬅️ Получено"
            response.append(
                f"{direction} {msg['timestamp'].strftime('%d.%m.%Y %H:%M')}\n"
                f"ID собеседника: {msg['receiver'] if msg['sender'] == user_id else msg['sender']}\n"
                f"Текст: {msg['text']}\n"
            )
        
        await update.message.reply_text("\n".join(response))
    
    elif mode == "search_id":
        search_term = text.strip()
        found_users = []
        
        # Поиск по анонимному ID
        for uid, data in users.items():
            if search_term.lower() in uid.lower():
                found_users.append((uid, data))
        
        # Поиск по Telegram ID
        if search_term.isdigit():
            tg_id = int(search_term)
            for uid, data in users.items():
                if data["tg_id"] == tg_id:
                    found_users.append((uid, data))
        
        if not found_users:
            await update.message.reply_text("Пользователи не найдены")
            return
        
        response = ["🔍 Результаты поиска:"]
        for uid, data in found_users[:5]:
            response.append(f"Анонимный ID: {uid}")
            response.append(f"Telegram ID: {data['tg_id']}")
            response.append(f"Контактов: {len(data['contacts'])}")
            response.append("------")
        
        await update.message.reply_text("\n".join(response))
    
    await admin_menu(update, context)

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

⚠️ *Важно:*
- Сообщения хранятся только 30 дней
- Не передавайте свой ID посторонним
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Обработка админских кнопок
    if user.id in ADMIN_IDS:
        if query.data == 'admin_view_chat':
            await admin_view_chat(update, context)
            return
        elif query.data == 'admin_search_id':
            await admin_search_id(update, context)
            return
        elif query.data == 'admin_stats':
            await admin_stats(update, context)
            return
        elif query.data == 'admin_back':
            await admin_menu(update, context)
            return
        elif query.data == 'admin_exit':
            await admin_exit(update, context)
            return
        elif query.data == 'start_menu':
            await start(update, context)
            return
    
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
            )
    
    elif query.data == 'new_contact':
        context.user_data["awaiting_contact_id"] = True
        await query.edit_message_text("✏️ Введите ID контакта:")
    
    elif query.data == 'show_id':
        await query.edit_message_text(f"🔑 Ваш ID:\n`{anon_id}`", parse_mode='Markdown')
    
    elif query.data == 'help':
        await help_command(update, context)
    
    elif query.data == 'back_to_main':
        keyboard = [
            [InlineKeyboardButton("Мои контакты", callback_data='contacts')],
            [InlineKeyboardButton("Написать контакту", callback_data='new_contact')],
            [InlineKeyboardButton("Мой ID", callback_data='show_id')],
            [InlineKeyboardButton("Помощь", callback_data='help')]
        ]
        await query.edit_message_text(
            "📱 Главное меню:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('write_'):
        contact_id = query.data[6:]
        if contact_id not in users[anon_id]["contacts"]:
            await query.edit_message_text("❌ Контакт не найден")
            return
        context.user_data["current_contact"] = contact_id
        await query.edit_message_text(f"✉️ Пишите сообщение для {contact_id[:8]}...:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    
    # Проверка на админское сообщение
    if user.id in ADMIN_IDS and context.user_data.get("admin_mode"):
        await handle_admin_message(update, context)
        return
    
    anon_id = next((uid for uid, data in users.items() if data["tg_id"] == user.id), None)
    
    if not anon_id:
        await update.message.reply_text("❌ Сессия устарела. Нажмите /start")
        return
    
    cleanup_old_messages()
    if pending_messages.get(anon_id):
        for msg in pending_messages[anon_id]:
            try:
                await update.message.reply_text(
                    f"📩 Сообщение от анонима:\n\n{msg['text']}\n\n"
                    f"🕒 {msg['timestamp'].strftime('%d.%m.%Y %H:%M')}"
                )
                # Запись в историю для админа
                all_messages.append({
                    "sender": msg['sender'],
                    "receiver": anon_id,
                    "text": msg['text'],
                    "timestamp": msg['timestamp']
                })
            except Exception as e:
                logger.error(f"Ошибка показа сообщения: {e}")
        pending_messages[anon_id] = []
        return
    
    if context.user_data.get("awaiting_contact_id"):
        contact_id = message_text.strip()
        
        if contact_id == anon_id:
            await update.message.reply_text("🚫 Нельзя добавить самого себя!")
        elif contact_id in users:
            if contact_id not in users[anon_id]["contacts"]:
                users[anon_id]["contacts"].append(contact_id)
                await update.message.reply_text(f"✅ Контакт добавлен!")
            else:
                await update.message.reply_text("ℹ️ Контакт уже есть в списке")
        else:
            await update.message.reply_text("❌ Пользователь не найден")
        
        context.user_data["awaiting_contact_id"] = False
        return
    
    if "current_contact" in context.user_data:
        contact_id = context.user_data["current_contact"]
        
        if contact_id not in users:
            await update.message.reply_text("❌ Контакт не найден")
            context.user_data.pop("current_contact", None)
            return
        
        if len(message_text) > 4000:
            await update.message.reply_text("❌ Слишком длинное сообщение (макс. 4000 символов)")
            return
        
        if contact_id not in pending_messages:
            pending_messages[contact_id] = []
        
        pending_messages[contact_id].append({
            "sender": anon_id,
            "text": message_text,
            "timestamp": datetime.now()
        })
        
        # Запись в историю для админа
        all_messages.append({
            "sender": anon_id,
            "receiver": contact_id,
            "text": message_text,
            "timestamp": datetime.now()
        })
        
        try:
            await context.bot.send_message(
                chat_id=users[contact_id]["tg_id"],
                text=f"🔔 У вас новое сообщение от анонима!\nОтправьте любое сообщение боту чтобы прочитать."
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")
        
        await update.message.reply_text("✅ Сообщение доставлено!")
        context.user_data.pop("current_contact", None)
        return
    
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
    application = ApplicationBuilder().token("ВАШ_ТОКЕН_БОТА").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()
