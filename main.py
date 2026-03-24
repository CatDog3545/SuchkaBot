import os
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from openai import AsyncOpenAI
from flask import Flask, request
import threading

# Загружаем переменные окружения
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-v1-YOUR_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free")

# OpenRouter через OpenAI SDK
openai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Путь к файлу данных
DATA_FILE = Path("user_data.json")

# Хранилище данных: {user_id: {"chats": {chat_id: {"name": str, "messages": []}}, "active_chat": chat_id}}
user_data = {}

# Flask приложение для health check
app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK', 200

# Глобальная переменная для приложения
application = None


def load_data():
    """Загрузить данные из файла"""
    global user_data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                user_data = json.load(f)
            # Конвертируем ключи user_id из str в int
            user_data = {int(k): v for k, v in user_data.items()}
            print(f"✅ Загружено данных пользователей: {len(user_data)}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки данных: {e}")
            user_data = {}
    else:
        print("📁 Файл данных не найден, создаём новый")
        user_data = {}


def save_data():
    """Сохранить данные в файл"""
    try:
        # Конвертируем ключи user_id из int в str для JSON
        data_to_save = {str(k): v for k, v in user_data.items()}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

# Главное меню
MAIN_MENU = ReplyKeyboardMarkup(
    [[KeyboardButton("📋 Список чатов"), KeyboardButton("➕ Новый чат")]],
    resize_keyboard=True
)

# Меню выбора чата (генерируется динамически)
def get_chats_menu(chat_names: list) -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(name)] for name in chat_names]
    keyboard.append([KeyboardButton("🔙 Назад в меню")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Кнопки меню
MENU_BUTTONS = {"📋 Список чатов", "➕ Новый чат", "🔙 Назад в меню"}


def get_user_chats(user_id: int) -> dict:
    """Получить данные пользователя или создать новые"""
    if user_id not in user_data:
        user_data[user_id] = {
            "chats": {},
            "active_chat": None
        }
    return user_data[user_id]


def create_new_chat(user_id: int, name: str = None) -> str:
    """Создать новый чат"""
    chat_id = str(uuid.uuid4())[:8]
    if not name:
        name = f"Чат {datetime.now().strftime('%d.%m %H:%M')}"

    user_chats = get_user_chats(user_id)
    user_chats["chats"][chat_id] = {
        "name": name,
        "messages": []
    }
    user_chats["active_chat"] = chat_id
    save_data()  # Сохраняем после создания чата
    return chat_id


def get_active_chat(user_id: int) -> dict:
    """Получить активный чат пользователя"""
    user_chats = get_user_chats(user_id)
    if user_chats["active_chat"] and user_chats["active_chat"] in user_chats["chats"]:
        return user_chats["chats"][user_chats["active_chat"]]
    return None


def switch_chat(user_id: int, chat_name: str) -> bool:
    """Переключиться на чат по названию"""
    user_chats = get_user_chats(user_id)
    for chat_id, chat_data in user_chats["chats"].items():
        if chat_data["name"] == chat_name:
            user_chats["active_chat"] = chat_id
            save_data()  # Сохраняем после переключения чата
            return True
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.message.chat_id
    get_user_chats(user_id)  # Инициализация

    await update.message.reply_text(
        "👋 Привет! Я AI-бот с поддержкой чатов.\n\n"
        "Используй кнопки внизу для управления чатами!",
        reply_markup=MAIN_MENU
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню"""
    await update.message.reply_text(
        "📋 Главное меню",
        reply_markup=MAIN_MENU
    )


async def show_chats_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список чатов"""
    user_id = update.message.chat_id
    user_chats = get_user_chats(user_id)

    if not user_chats["chats"]:
        await update.message.reply_text(
            "📭 У вас пока нет чатов.\nСоздайте новый чат кнопкой «➕ Новый чат»",
            reply_markup=MAIN_MENU
        )
        return

    # Получаем список названий чатов
    chat_names = [chat["name"] for chat in user_chats["chats"].values()]
    active_chat = get_active_chat(user_id)
    active_name = active_chat["name"] if active_chat else None

    # Формируем сообщение
    message = "📋 **Ваши чаты:**\n\n"
    for chat_id, chat_data in user_chats["chats"].items():
        marker = "🟢" if chat_data["name"] == active_name else "⚪"
        message += f"{marker} {chat_data['name']}\n"

    await update.message.reply_text(
        message,
        reply_markup=get_chats_menu(chat_names)
    )


async def create_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новый чат"""
    user_id = update.message.chat_id
    chat_id = create_new_chat(user_id)
    active_chat = get_active_chat(user_id)

    await update.message.reply_text(
        f"✅ Создан новый чат: **{active_chat['name']}**\n\n"
        f"ID: `{chat_id}`\n\n"
        "Напишите сообщение, чтобы начать диалог!",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню"""
    await update.message.reply_text(
        "🔙 Возврат в главное меню",
        reply_markup=MAIN_MENU
    )


async def handle_chat_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора чата из списка"""
    user_id = update.message.chat_id
    chat_name = update.message.text

    if switch_chat(user_id, chat_name):
        active_chat = get_active_chat(user_id)
        # Показываем последние сообщения
        messages = active_chat["messages"][-5:] if active_chat else []

        if messages:
            preview = "\n".join([f"{m['role']}: {m['content'][:50]}..." for m in messages])
            await update.message.reply_text(
                f"✅ Переключен на чат: **{chat_name}**\n\n"
                f"Последние сообщения:\n_{preview}_",
                parse_mode="Markdown",
                reply_markup=get_chats_menu([chat_name])
            )
        else:
            await update.message.reply_text(
                f"✅ Переключен на чат: **{chat_name}**\n\n"
                "Чат пуст, напишите первое сообщение!",
                parse_mode="Markdown",
                reply_markup=get_chats_menu([chat_name])
            )
    else:
        await update.message.reply_text(
            "❌ Чат не найден. Выберите чат из списка.",
            reply_markup=MAIN_MENU
        )


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок меню"""
    text = update.message.text

    if text == "📋 Список чатов":
        await show_chats_list(update, context)
    elif text == "➕ Новый чат":
        await create_chat(update, context)
    elif text == "🔙 Назад в меню":
        await back_to_menu(update, context)


async def handle_message_or_chat_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений и выбор чата"""
    text = update.message.text
    user_id = update.message.chat_id
    user_chats = get_user_chats(user_id)

    # Проверяем, является ли текст названием чата
    chat_exists = any(chat["name"] == text for chat in user_chats["chats"].values())

    if chat_exists:
        # Это выбор чата
        if switch_chat(user_id, text):
            active_chat = get_active_chat(user_id)
            messages = active_chat["messages"][-5:] if active_chat else []

            if messages:
                preview = "\n".join([f"{m['role']}: {m['content'][:50]}..." for m in messages])
                await update.message.reply_text(
                    f"✅ Переключен на чат: **{text}**\n\n"
                    f"Последние сообщения:\n_{preview}_",
                    parse_mode="Markdown",
                    reply_markup=get_chats_menu([text])
                )
            else:
                await update.message.reply_text(
                    f"✅ Переключен на чат: **{text}**\n\n"
                    "Чат пуст, напишите первое сообщение!",
                    parse_mode="Markdown",
                    reply_markup=get_chats_menu([text])
                )
    else:
        # Это сообщение для ИИ
        await handle_message(update, context)


# Статусы для отображения процесса "мышления" ИИ
THINKING_STATUSES = [
    "🤔 Анализирую вопрос...",
    "💭 Обдумываю ответ...",
    "🔍 Ищу информацию...",
    "✍️ Формулирую ответ...",
]


async def show_thinking_process(update: Update):
    """Показывает постепенный процесс 'мышления' ИИ"""
    for status in THINKING_STATUSES:
        await update.message.chat.send_action(action="typing")
        await asyncio.sleep(0.7)


async def stream_response(update: Update, active_chat: dict):
    """Потоковая отправка ответа от ИИ (streaming) через OpenAI SDK"""
    full_response = ""
    message = None
    last_edit_time = 0

    try:
        # Создаём сообщение-заглушку
        message = await update.message.reply_text("⏳")
        last_edit_time = asyncio.get_event_loop().time()

        # Streaming запрос через OpenAI SDK
        stream = await openai_client.chat.completions.create(
            model=MODEL,
            messages=active_chat["messages"],
            stream=True
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            content = delta.content if delta else None

            if content:
                full_response += content

                # Ограничиваем частоту редактирований (Telegram limit)
                current_time = asyncio.get_event_loop().time()
                if current_time - last_edit_time >= 1.0:  # Задержка 1 сек
                    await message.edit_text(full_response[:4096])
                    last_edit_time = current_time

        # Финальное обновление
        if full_response:
            await message.edit_text(full_response[:4096])
            active_chat["messages"].append({"role": "assistant", "content": full_response})
            save_data()

    except BadRequest as e:
        error_text = str(e)
        if "message is not modified" not in error_text and "rate limit" not in error_text.lower():
            if message:
                await message.edit_text(f"{full_response[:4000]}\n\n_⚠️ Ошибка: {type(e).__name__}_", parse_mode="Markdown")
        # Всё равно сохраняем ответ
        if full_response:
            active_chat["messages"].append({"role": "assistant", "content": full_response})
            save_data()
    except Exception as e:
        if message:
            await message.edit_text(f"{full_response[:4000]}\n\n❌ {type(e).__name__}: {str(e)}")
        else:
            await update.message.reply_text(f"❌ {type(e).__name__}: {str(e)}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений для ИИ"""
    user_id = update.message.chat_id
    user_message = update.message.text

    # Получаем активный чат или создаём новый
    active_chat = get_active_chat(user_id)
    if not active_chat:
        create_new_chat(user_id)
        active_chat = get_active_chat(user_id)

    # Добавляем сообщение в историю
    active_chat["messages"].append({"role": "user", "content": user_message})

    # Показываем процесс "мышления"
    await show_thinking_process(update)

    # Потоковая отправка ответа
    await stream_response(update, active_chat)


def main():
    """Запуск бота"""
    global application
    
    # Загружаем данные из файла
    load_data()

    # Проверка переменных окружения
    print(f"🔍 TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith('_YOUR_TELEGRAM_BOT_TOKEN') else '❌'}")
    print(f"🔍 OPENROUTER_API_KEY: {'✅' if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.endswith('_YOUR_API_KEY') else '❌'}")
    print(f"🔍 OPENROUTER_MODEL: {MODEL}")
    
    # Определяем режим запуска
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    
    if RENDER_EXTERNAL_URL:
        # Режим Render (webhook)
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", show_menu))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(📋 Список чатов|➕ Новый чат|🔙 Назад в меню)$'),
            handle_button_click
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message_or_chat_select
        ))
        
        # Запускаем Flask для webhook и health check
        def run_flask():
            app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
        
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        
        print(f"🤖 Бот запущен на Render: {RENDER_EXTERNAL_URL}")
        
        # Запускаем бота в режиме webhook
        application.run_webhook(
            listen='0.0.0.0',
            port=int(os.getenv('PORT', 8080)),
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
        )
    else:
        # Локальный режим (polling)
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", show_menu))

        # Обработчик кнопок меню
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(📋 Список чатов|➕ Новый чат|🔙 Назад в меню)$'),
            handle_button_click
        ))

        # Обработчик выбора чата из списка
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message_or_chat_select
        ))

        print("🤖 Бот запущен... (Ctrl+C для остановки)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
