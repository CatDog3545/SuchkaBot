import os
import json
import uuid
import hmac
import hashlib
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import parse_qs, unquote

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
DEV_USER_ID = int(os.getenv("DEV_USER_ID", "6473460730"))

openai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

DATA_FILE = Path("user_data.json")
user_data: Dict[int, Any] = {}

app = FastAPI(title="SuchkaBot Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class SendMessageRequest(BaseModel):
    chat_id: str
    message: str


class CreateChatRequest(BaseModel):
    name: Optional[str] = None


class RenameChatRequest(BaseModel):
    name: str


class ChatInfo(BaseModel):
    chat_id: str
    name: str
    last_message: Optional[str] = None
    last_message_time: Optional[str] = None
    message_count: int


class ChatDetail(BaseModel):
    chat_id: str
    name: str
    messages: list[Message]


def load_data():
    global user_data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            user_data = {int(k): v for k, v in raw.items()}
        except Exception as e:
            print(f"Error loading data: {e}")
            user_data = {}


def save_data():
    try:
        raw = {str(k): v for k, v in user_data.items()}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")


def validate_init_data(init_data: str) -> dict:
    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=500, detail="TELEGRAM_TOKEN not configured")

    parsed = parse_qs(init_data)
    hash_value = parsed.get("hash", [""])[0]

    data_check = []
    for key in sorted(parsed.keys()):
        if key == "hash":
            continue
        values = parsed[key]
        if len(values) == 1:
            data_check.append(f"{key}={unquote(values[0])}")

    data_check_string = "\n".join(data_check)

    secret_key = hmac.new(
        b"WebAppData",
        TELEGRAM_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, hash_value):
        raise HTTPException(status_code=401, detail="Invalid initData signature")

    user_str = parsed.get("user", [""])[0]
    if not user_str:
        raise HTTPException(status_code=401, detail="No user in initData")

    return json.loads(unquote(user_str))


async def get_user_id(request: Request) -> int:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            init_data = auth_header[7:]

    if not init_data:
        if DEV_MODE:
            print(f"[DEV] Bypassing auth, using DEV_USER_ID={DEV_USER_ID}")
            return DEV_USER_ID
        raise HTTPException(status_code=401, detail="Missing initData")

    user_info = validate_init_data(init_data)
    return int(user_info["id"])


def get_user_chats(user_id: int) -> dict:
    if user_id not in user_data:
        user_data[user_id] = {"chats": {}, "active_chat": None}
    return user_data[user_id]


def get_active_chat(user_id: int) -> dict:
    user_chats = get_user_chats(user_id)
    if user_chats["active_chat"] and user_chats["active_chat"] in user_chats["chats"]:
        return user_chats["chats"][user_chats["active_chat"]]
    return None


def switch_chat(user_id: int, chat_name: str) -> bool:
    user_chats = get_user_chats(user_id)
    for chat_id, chat_data in user_chats["chats"].items():
        if chat_data["name"] == chat_name:
            user_chats["active_chat"] = chat_id
            save_data()
            return True
    return False


def create_new_chat(user_id: int, name: str = None) -> str:
    chat_id = str(uuid.uuid4())[:8]
    if not name:
        name = f"Чат {datetime.now().strftime('%d.%m %H:%M')}"

    user_chats = get_user_chats(user_id)
    user_chats["chats"][chat_id] = {
        "name": name,
        "messages": [],
        "created_at": datetime.now().isoformat(),
    }
    user_chats["active_chat"] = chat_id
    save_data()


def run_telegram_bot():
    """Запуск Telegram бота в отдельном потоке"""
    import asyncio
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from telegram.error import BadRequest
    from openai import AsyncOpenAI

    bot_openai = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    MAIN_MENU = ReplyKeyboardMarkup(
        [[KeyboardButton("📋 Список чатов"), KeyboardButton("➕ Новый чат")]],
        resize_keyboard=True
    )

    def get_chats_menu(chat_names):
        keyboard = [[KeyboardButton(name)] for name in chat_names]
        keyboard.append([KeyboardButton("🔙 Назад в меню")])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    THINKING_STATUSES = [
        "🤔 Анализирую вопрос...",
        "💭 Обдумываю ответ...",
        "🔍 Ищу информацию...",
        "✍️ Формулирую ответ...",
    ]

    async def show_thinking(update):
        for status in THINKING_STATUSES:
            try:
                await update.message.chat.send_action(action="typing")
                await asyncio.sleep(0.7)
            except Exception:
                break

    async def stream_response(update, active_chat):
        full_response = ""
        message = None
        last_edit_time = 0

        try:
            message = await update.message.reply_text("⏳")
            last_edit_time = asyncio.get_event_loop().time()

            stream = await bot_openai.chat.completions.create(
                model=MODEL,
                messages=active_chat["messages"],
                stream=True
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = delta.content if delta else None
                if content:
                    full_response += content
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_edit_time >= 1.0:
                        try:
                            await message.edit_text(full_response[:4096])
                            last_edit_time = current_time
                        except Exception:
                            pass

            if full_response:
                await message.edit_text(full_response[:4096])
                active_chat["messages"].append({"role": "assistant", "content": full_response})
                save_data()

        except BadRequest as e:
            error_text = str(e)
            if "message is not modified" not in error_text and "rate limit" not in error_text.lower():
                if message:
                    try:
                        await message.edit_text(f"{full_response[:4000]}\n\n_⚠️ Ошибка: {type(e).__name__}_", parse_mode="Markdown")
                    except Exception:
                        pass
            if full_response:
                active_chat["messages"].append({"role": "assistant", "content": full_response})
                save_data()
        except Exception as e:
            if message:
                try:
                    await message.edit_text(f"{full_response[:4000]}\n\n❌ {type(e).__name__}: {str(e)}")
                except Exception:
                    pass
            else:
                try:
                    await update.message.reply_text(f"❌ {type(e).__name__}: {str(e)}")
                except Exception:
                    pass

    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        get_user_chats(user_id)
        await update.message.reply_text(
            "👋 Привет! Я AI-бот с поддержкой чатов.\n\n"
            "Используй кнопки внизу для управления чатами!",
            reply_markup=MAIN_MENU
        )

    async def show_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📋 Главное меню", reply_markup=MAIN_MENU)

    async def show_chats_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        user_chats = get_user_chats(user_id)
        if not user_chats["chats"]:
            await update.message.reply_text(
                "📭 У вас пока нет чатов.\nСоздайте новый чат кнопкой «➕ Новый чат»",
                reply_markup=MAIN_MENU
            )
            return
        chat_names = [chat["name"] for chat in user_chats["chats"].values()]
        active_chat = get_active_chat(user_id)
        active_name = active_chat["name"] if active_chat else None
        message = "📋 **Ваши чаты:**\n\n"
        for chat_id, chat_data in user_chats["chats"].items():
            marker = "🟢" if chat_data["name"] == active_name else "⚪"
            message += f"{marker} {chat_data['name']}\n"
        await update.message.reply_text(message, reply_markup=get_chats_menu(chat_names))

    async def create_chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def back_to_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=MAIN_MENU)

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        user_message = update.message.text
        active_chat = get_active_chat(user_id)
        if not active_chat:
            create_new_chat(user_id)
            active_chat = get_active_chat(user_id)
        active_chat["messages"].append({"role": "user", "content": user_message})
        await show_thinking(update)
        await stream_response(update, active_chat)

    async def handle_chat_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        chat_name = update.message.text
        if switch_chat(user_id, chat_name):
            active_chat = get_active_chat(user_id)
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
            await update.message.reply_text("❌ Чат не найден. Выберите чат из списка.", reply_markup=MAIN_MENU)

    async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "📋 Список чатов":
            await show_chats_list_cmd(update, context)
        elif text == "➕ Новый чат":
            await create_chat_cmd(update, context)
        elif text == "🔙 Назад в меню":
            await back_to_menu_cmd(update, context)

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        user_id = update.message.chat_id
        user_chats = get_user_chats(user_id)
        chat_exists = any(chat["name"] == text for chat in user_chats["chats"].values())
        if chat_exists:
            await handle_chat_select(update, context)
        else:
            await handle_message(update, context)

    def bot_main():
        load_data()
        print(f"🔍 TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith('_YOUR_TELEGRAM_BOT_TOKEN') else '❌'}")
        print(f"🔍 OPENROUTER_API_KEY: {'✅' if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.endswith('_YOUR_API_KEY') else '❌'}")
        print(f"🔍 OPENROUTER_MODEL: {MODEL}")

        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("menu", show_menu_cmd))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(📋 Список чатов|➕ Новый чат|🔙 Назад в меню)$'),
            handle_buttons
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        ))
        print("🤖 Бот запущен...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    thread = threading.Thread(target=bot_main, daemon=True)
    thread.start()
    print("🤖 Telegram bot thread started")


@app.on_event("startup")
def startup():
    load_data()
    print(f"Loaded data for {len(user_data)} users")
    if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith("_YOUR_TELEGRAM_BOT_TOKEN"):
        run_telegram_bot()


def run_telegram_bot():
    """Запуск Telegram бота в отдельном потоке"""
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from telegram.error import BadRequest
    from openai import AsyncOpenAI

    bot_openai = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    MAIN_MENU = ReplyKeyboardMarkup(
        [[KeyboardButton("📋 Список чатов"), KeyboardButton("➕ Новый чат")]],
        resize_keyboard=True
    )

    def get_chats_menu(chat_names):
        keyboard = [[KeyboardButton(name)] for name in chat_names]
        keyboard.append([KeyboardButton("🔙 Назад в меню")])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    THINKING_STATUSES = [
        "🤔 Анализирую вопрос...",
        "💭 Обдумываю ответ...",
        "🔍 Ищу информацию...",
        "✍️ Формулирую ответ...",
    ]

    async def show_thinking(update):
        for status in THINKING_STATUSES:
            try:
                await update.message.chat.send_action(action="typing")
                await asyncio.sleep(0.7)
            except Exception:
                break

    async def stream_response(update, active_chat):
        full_response = ""
        message = None
        last_edit_time = 0
        try:
            message = await update.message.reply_text("⏳")
            last_edit_time = asyncio.get_event_loop().time()
            stream = await bot_openai.chat.completions.create(
                model=MODEL, messages=active_chat["messages"], stream=True
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = delta.content if delta else None
                if content:
                    full_response += content
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_edit_time >= 1.0:
                        try:
                            await message.edit_text(full_response[:4096])
                            last_edit_time = current_time
                        except Exception:
                            pass
            if full_response:
                await message.edit_text(full_response[:4096])
                active_chat["messages"].append({"role": "assistant", "content": full_response})
                save_data()
        except BadRequest as e:
            error_text = str(e)
            if "message is not modified" not in error_text and "rate limit" not in error_text.lower():
                if message:
                    try:
                        await message.edit_text(f"{full_response[:4000]}\n\n_⚠️ Ошибка: {type(e).__name__}_", parse_mode="Markdown")
                    except Exception:
                        pass
            if full_response:
                active_chat["messages"].append({"role": "assistant", "content": full_response})
                save_data()
        except Exception as e:
            if message:
                try:
                    await message.edit_text(f"{full_response[:4000]}\n\n❌ {type(e).__name__}: {str(e)}")
                except Exception:
                    pass
            else:
                try:
                    await update.message.reply_text(f"❌ {type(e).__name__}: {str(e)}")
                except Exception:
                    pass

    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        get_user_chats(user_id)
        await update.message.reply_text(
            "👋 Привет! Я AI-бот с поддержкой чатов.\n\nИспользуй кнопки внизу для управления чатами!",
            reply_markup=MAIN_MENU
        )

    async def show_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📋 Главное меню", reply_markup=MAIN_MENU)

    async def show_chats_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        user_chats = get_user_chats(user_id)
        if not user_chats["chats"]:
            await update.message.reply_text(
                "📭 У вас пока нет чатов.\nСоздайте новый чат кнопкой «➕ Новый чат»",
                reply_markup=MAIN_MENU
            )
            return
        chat_names = [chat["name"] for chat in user_chats["chats"].values()]
        active_chat = get_active_chat(user_id)
        active_name = active_chat["name"] if active_chat else None
        message = "📋 **Ваши чаты:**\n\n"
        for chat_id, chat_data in user_chats["chats"].items():
            marker = "🟢" if chat_data["name"] == active_name else "⚪"
            message += f"{marker} {chat_data['name']}\n"
        await update.message.reply_text(message, reply_markup=get_chats_menu(chat_names))

    async def create_chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        chat_id = create_new_chat(user_id)
        active_chat = get_active_chat(user_id)
        await update.message.reply_text(
            f"✅ Создан новый чат: **{active_chat['name']}**\n\n"
            f"ID: `{chat_id}`\n\n"
            "Напишите сообщение, чтобы начать диалог!",
            parse_mode="Markdown", reply_markup=MAIN_MENU
        )

    async def back_to_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=MAIN_MENU)

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        user_message = update.message.text
        active_chat = get_active_chat(user_id)
        if not active_chat:
            create_new_chat(user_id)
            active_chat = get_active_chat(user_id)
        active_chat["messages"].append({"role": "user", "content": user_message})
        await show_thinking(update)
        await stream_response(update, active_chat)

    async def handle_chat_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.chat_id
        chat_name = update.message.text
        if switch_chat(user_id, chat_name):
            active_chat = get_active_chat(user_id)
            messages = active_chat["messages"][-5:] if active_chat else []
            if messages:
                preview = "\n".join([f"{m['role']}: {m['content'][:50]}..." for m in messages])
                await update.message.reply_text(
                    f"✅ Переключен на чат: **{chat_name}**\n\n"
                    f"Последние сообщения:\n_{preview}_",
                    parse_mode="Markdown", reply_markup=get_chats_menu([chat_name])
                )
            else:
                await update.message.reply_text(
                    f"✅ Переключен на чат: **{chat_name}**\n\n"
                    "Чат пуст, напишите первое сообщение!",
                    parse_mode="Markdown", reply_markup=get_chats_menu([chat_name])
                )
        else:
            await update.message.reply_text("❌ Чат не найден. Выберите чат из списка.", reply_markup=MAIN_MENU)

    async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "📋 Список чатов":
            await show_chats_list_cmd(update, context)
        elif text == "➕ Новый чат":
            await create_chat_cmd(update, context)
        elif text == "🔙 Назад в меню":
            await back_to_menu_cmd(update, context)

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        user_id = update.message.chat_id
        user_chats = get_user_chats(user_id)
        chat_exists = any(chat["name"] == text for chat in user_chats["chats"].values())
        if chat_exists:
            await handle_chat_select(update, context)
        else:
            await handle_message(update, context)

    def bot_main():
        load_data()
        print(f"🔍 TELEGRAM_TOKEN: {'✅' if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith('_YOUR_TELEGRAM_BOT_TOKEN') else '❌'}")
        print(f"🔍 OPENROUTER_API_KEY: {'✅' if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.endswith('_YOUR_API_KEY') else '❌'}")
        print(f"🔍 OPENROUTER_MODEL: {MODEL}")
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("menu", show_menu_cmd))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(📋 Список чатов|➕ Новый чат|🔙 Назад в меню)$'),
            handle_buttons
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_text
        ))
        print("🤖 Бот запущен...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    thread = threading.Thread(target=bot_main, daemon=True)
    thread.start()
    print("🤖 Telegram bot thread started")
    if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith("_YOUR_TELEGRAM_BOT_TOKEN"):
        run_telegram_bot()


@app.get("/health")
async def health():
    return {"status": "ok"}


DIST_DIR = Path("dist")

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")


@app.get("/api/chats", response_model=list[ChatInfo])
async def list_chats(user_id: int = Depends(get_user_id)):
    user_chats = get_user_chats(user_id)
    result = []

    for cid, cdata in user_chats["chats"].items():
        messages = cdata.get("messages", [])
        last_msg = messages[-1] if messages else None

        result.append(ChatInfo(
            chat_id=cid,
            name=cdata["name"],
            last_message=last_msg["content"][:100] if last_msg else None,
            last_message_time=cdata.get("updated_at"),
            message_count=len(messages),
        ))

    result.sort(key=lambda x: x.last_message_time or "", reverse=True)
    return result


@app.get("/api/chats/{chat_id}", response_model=ChatDetail)
async def get_chat(chat_id: str, user_id: int = Depends(get_user_id)):
    user_chats = get_user_chats(user_id)

    if chat_id not in user_chats["chats"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    cdata = user_chats["chats"][chat_id]
    return ChatDetail(
        chat_id=chat_id,
        name=cdata["name"],
        messages=[Message(**m) for m in cdata.get("messages", [])],
    )


@app.post("/api/chats", response_model=ChatDetail)
async def create_chat(req: CreateChatRequest, user_id: int = Depends(get_user_id)):
    chat_id = create_new_chat(user_id, req.name)
    cdata = user_data[user_id]["chats"][chat_id]

    return ChatDetail(
        chat_id=chat_id,
        name=cdata["name"],
        messages=[],
    )


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, user_id: int = Depends(get_user_id)):
    user_chats = get_user_chats(user_id)

    if chat_id not in user_chats["chats"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    del user_chats["chats"][chat_id]
    if user_chats["active_chat"] == chat_id:
        remaining = list(user_chats["chats"].keys())
        user_chats["active_chat"] = remaining[0] if remaining else None

    save_data()
    return {"status": "ok"}


@app.patch("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, req: RenameChatRequest, user_id: int = Depends(get_user_id)):
    user_chats = get_user_chats(user_id)

    if chat_id not in user_chats["chats"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_chats["chats"][chat_id]["name"] = req.name
    save_data()
    return {"status": "ok", "name": req.name}


@app.post("/api/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    req: SendMessageRequest,
    user_id: int = Depends(get_user_id),
):
    user_chats = get_user_chats(user_id)

    if chat_id not in user_chats["chats"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    cdata = user_chats["chats"][chat_id]
    cdata["messages"].append({"role": "user", "content": req.message})
    cdata["updated_at"] = datetime.now().isoformat()

    if cdata["name"].startswith("Чат ") and len(cdata["messages"]) == 1:
        cdata["name"] = req.message[:50]

    save_data()

    try:
        response = await openai_client.chat.completions.create(
            model=MODEL,
            messages=cdata["messages"],
            stream=False,
        )

        assistant_msg = response.choices[0].message.content or ""
        cdata["messages"].append({"role": "assistant", "content": assistant_msg})
        cdata["updated_at"] = datetime.now().isoformat()
        save_data()

        return {"response": assistant_msg}

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI error: {str(e)}")


@app.post("/api/chats/{chat_id}/messages/stream")
async def stream_message(
    chat_id: str,
    req: SendMessageRequest,
    user_id: int = Depends(get_user_id),
):
    user_chats = get_user_chats(user_id)

    if chat_id not in user_chats["chats"]:
        raise HTTPException(status_code=404, detail="Chat not found")

    cdata = user_chats["chats"][chat_id]
    cdata["messages"].append({"role": "user", "content": req.message})
    cdata["updated_at"] = datetime.now().isoformat()

    if cdata["name"].startswith("Чат ") and len(cdata["messages"]) == 1:
        cdata["name"] = req.message[:50]

    save_data()

    async def event_generator():
        full_response = ""
        try:
            stream = await openai_client.chat.completions.create(
                model=MODEL,
                messages=cdata["messages"],
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = delta.content if delta else None

                if content:
                    full_response += content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': content}, ensure_ascii=False)}\n\n"

            cdata["messages"].append({"role": "assistant", "content": full_response})
            cdata["updated_at"] = datetime.now().isoformat()
            save_data()

            yield f"data: {json.dumps({'type': 'done', 'content': full_response}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("RAILWAY_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
