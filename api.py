import os
import json
import uuid
import hmac
import hashlib
import asyncio
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
    uvicorn.run(app, host="0.0.0.0", port=8080)
