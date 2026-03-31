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
    secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
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
    return chat_id


@app.on_event("startup")
def startup():
    load_data()
    print(f"Loaded data for {len(user_data)} users")
    if TELEGRAM_TOKEN and not TELEGRAM_TOKEN.endswith("_YOUR_TELEGRAM_BOT_TOKEN"):
        threading.Thread(target=_run_bot_thread, daemon=True).start()
        print("🤖 Telegram bot starting in background thread...")


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
    return ChatDetail(chat_id=chat_id, name=cdata["name"], messages=[])


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
async def send_message(chat_id: str, req: SendMessageRequest, user_id: int = Depends(get_user_id)):
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
            model=MODEL, messages=cdata["messages"], stream=False,
        )
        assistant_msg = response.choices[0].message.content or ""
        cdata["messages"].append({"role": "assistant", "content": assistant_msg})
        cdata["updated_at"] = datetime.now().isoformat()
        save_data()
        return {"response": assistant_msg}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI error: {str(e)}")


@app.post("/api/chats/{chat_id}/messages/stream")
async def stream_message(chat_id: str, req: SendMessageRequest, user_id: int = Depends(get_user_id)):
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
                model=MODEL, messages=cdata["messages"], stream=True,
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
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _run_bot_thread():
    """Telegram bot running in a background daemon thread."""
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from telegram.error import BadRequest
    from openai import AsyncOpenAI

    bot_openai = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

    MAIN_MENU = ReplyKeyboardMarkup(
        [[KeyboardButton("📋 Список чатов"), KeyboardButton("➕ Новый чат")]],
        resize_keyboard=True
    )

    def get_chats_menu(chat_names):
        keyboard = [[KeyboardButton(name)] for name in chat_names]
        keyboard.append([KeyboardButton("🔙 Назад в меню")])
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    THINKING = ["🤔 Анализирую вопрос...", "💭 Обдумываю ответ...", "🔍 Ищу информацию...", "✍️ Формулирую ответ..."]

    async def show_thinking(update):
        for s in THINKING:
            try:
                await update.message.chat.send_action(action="typing")
                await asyncio.sleep(0.7)
            except Exception:
                break

    async def stream_resp(update, active_chat):
        full = ""
        msg = None
        last_t = 0
        try:
            msg = await update.message.reply_text("⏳")
            last_t = asyncio.get_event_loop().time()
            stream = await bot_openai.chat.completions.create(model=MODEL, messages=active_chat["messages"], stream=True)
            async for chunk in stream:
                c = chunk.choices[0].delta.content if chunk.choices[0].delta else None
                if c:
                    full += c
                    now = asyncio.get_event_loop().time()
                    if now - last_t >= 1.0:
                        try:
                            await msg.edit_text(full[:4096])
                            last_t = now
                        except Exception:
                            pass
            if full:
                await msg.edit_text(full[:4096])
                active_chat["messages"].append({"role": "assistant", "content": full})
                save_data()
        except BadRequest as e:
            if "message is not modified" not in str(e) and "rate limit" not in str(e).lower():
                if msg:
                    try:
                        await msg.edit_text(f"{full[:4000]}\n\n_⚠️ {type(e).__name__}_", parse_mode="Markdown")
                    except Exception:
                        pass
            if full:
                active_chat["messages"].append({"role": "assistant", "content": full})
                save_data()
        except Exception as e:
            if msg:
                try:
                    await msg.edit_text(f"{full[:4000]}\n\n❌ {type(e).__name__}: {e}")
                except Exception:
                    pass
            else:
                try:
                    await update.message.reply_text(f"❌ {type(e).__name__}: {e}")
                except Exception:
                    pass

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        get_user_chats(uid)
        await update.message.reply_text("👋 Привет! Я AI-бот с поддержкой чатов.\n\nИспользуй кнопки внизу!", reply_markup=MAIN_MENU)

    async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📋 Главное меню", reply_markup=MAIN_MENU)

    async def cmd_chats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        uc = get_user_chats(uid)
        if not uc["chats"]:
            await update.message.reply_text("📭 Нет чатов. Создайте через «➕ Новый чат»", reply_markup=MAIN_MENU)
            return
        names = [c["name"] for c in uc["chats"].values()]
        ac = get_active_chat(uid)
        an = ac["name"] if ac else None
        msg = "📋 **Ваши чаты:**\n\n"
        for cid, cd in uc["chats"].items():
            msg += f"{'🟢' if cd['name'] == an else '⚪'} {cd['name']}\n"
        await update.message.reply_text(msg, reply_markup=get_chats_menu(names))

    async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        cid = create_new_chat(uid)
        ac = get_active_chat(uid)
        await update.message.reply_text(f"✅ Чат: **{ac['name']}**\nID: `{cid}`\n\nНапишите сообщение!", parse_mode="Markdown", reply_markup=MAIN_MENU)

    async def cmd_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔙 Назад", reply_markup=MAIN_MENU)

    async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        ac = get_active_chat(uid)
        if not ac:
            create_new_chat(uid)
            ac = get_active_chat(uid)
        ac["messages"].append({"role": "user", "content": update.message.text})
        await show_thinking(update)
        await stream_resp(update, ac)

    async def handle_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        name = update.message.text
        if switch_chat(uid, name):
            ac = get_active_chat(uid)
            msgs = ac["messages"][-5:] if ac else []
            if msgs:
                prev = "\n".join([f"{m['role']}: {m['content'][:50]}..." for m in msgs])
                await update.message.reply_text(f"✅ Чат: **{name}**\n\n_{prev}_", parse_mode="Markdown", reply_markup=get_chats_menu([name]))
            else:
                await update.message.reply_text(f"✅ Чат: **{name}**\n\nЧат пуст!", parse_mode="Markdown", reply_markup=get_chats_menu([name]))
        else:
            await update.message.reply_text("❌ Чат не найден.", reply_markup=MAIN_MENU)

    async def handle_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        t = update.message.text
        if t == "📋 Список чатов":
            await cmd_chats(update, ctx)
        elif t == "➕ Новый чат":
            await cmd_new(update, ctx)
        elif t == "🔙 Назад в меню":
            await cmd_back(update, ctx)

    async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.message.chat_id
        uc = get_user_chats(uid)
        if any(c["name"] == update.message.text for c in uc["chats"].values()):
            await handle_select(update, ctx)
        else:
            await handle_msg(update, ctx)

    def bot_main():
        load_data()
        print(f"🤖 Bot starting...")
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", cmd_start))
        application.add_handler(CommandHandler("menu", cmd_menu))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(📋 Список чатов|➕ Новый чат|🔙 Назад в меню)$'),
            handle_buttons
        ))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        print("🤖 Bot polling started...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    bot_main()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("RAILWAY_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port)
