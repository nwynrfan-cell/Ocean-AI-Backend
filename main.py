import os
import sqlite3
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# =========================================================
# Ocean AI
# Professional FastAPI Backend
# =========================================================

APP_NAME = "Ocean AI"
APP_VERSION = "1.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ocean_ai.db")

# ---------------------------------------------------------
# AI Provider Settings
# این موارد را در Railway → Variables قرار بده
# ---------------------------------------------------------

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_API_URL = os.getenv(
    "AI_API_URL",
    "https://api.openai.com/v1/chat/completions"
)
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

# ---------------------------------------------------------
# FastAPI
# ---------------------------------------------------------

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Ocean AI professional artificial intelligence API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# Database
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_used TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# Helpers
# =========================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_token():
    return secrets.token_urlsafe(48)


def save_message(user_id: str, role: str, content: str):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO messages
        (user_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, role, content, now_iso())
    )

    conn.commit()
    conn.close()


def authenticate(authorization: Optional[str]):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization format"
        )

    token = authorization.replace("Bearer ", "", 1).strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    token_hash = hash_text(token)

    conn = get_db()

    user = conn.execute(
        """
        SELECT user_id
        FROM sessions
        WHERE token_hash = ?
        """,
        (token_hash,)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid"
        )

    conn.execute(
        """
        UPDATE sessions
        SET last_used = ?
        WHERE token_hash = ?
        """,
        (now_iso(), token_hash)
    )

    conn.commit()
    conn.close()

    return user["user_id"]


# =========================================================
# Models
# =========================================================

class RegisterRequest(BaseModel):
    user_id: str
    password: str


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ChatRequest(BaseModel):
    message: str


# =========================================================
# Root
# =========================================================

@app.get("/")
def root():
    return {
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "message": "Ocean AI Server Online"
    }


# =========================================================
# Health
# =========================================================

@app.get("/api/health")
def health():
    return {
        "success": True,
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "ai_configured": bool(AI_API_KEY)
    }


# =========================================================
# Register
# =========================================================

@app.post("/api/auth/register")
def register(data: RegisterRequest):

    user_id = data.user_id.strip()
    password = data.password

    if len(user_id) < 3:
        raise HTTPException(
            status_code=400,
            detail="User ID must contain at least 3 characters"
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters"
        )

    password_hash = hash_text(password)

    conn = get_db()

    existing = conn.execute(
        """
        SELECT id
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    if existing:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="User already exists"
        )

    conn.execute(
        """
        INSERT INTO users
        (user_id, password_hash, created_at)
        VALUES (?, ?, ?)
        """,
        (user_id, password_hash, now_iso())
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Registration successful",
        "user_id": user_id
    }


# =========================================================
# Login
# =========================================================

@app.post("/api/auth/login")
def login(data: LoginRequest):

    user_id = data.user_id.strip()
    password_hash = hash_text(data.password)

    conn = get_db()

    user = conn.execute(
        """
        SELECT user_id
        FROM users
        WHERE user_id = ?
        AND password_hash = ?
        """,
        (user_id, password_hash)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="Invalid user ID or password"
        )

    token = create_token()
    token_hash = hash_text(token)

    conn.execute(
        """
        INSERT INTO sessions
        (user_id, token_hash, created_at, last_used)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            token_hash,
            now_iso(),
            now_iso()
        )
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Login successful",
        "user_id": user_id,
        "token": token
    }


# =========================================================
# Current User
# =========================================================

@app.get("/api/auth/me")
def me(
    authorization: Optional[str] = Header(default=None)
):

    user_id = authenticate(authorization)

    conn = get_db()

    user = conn.execute(
        """
        SELECT user_id, created_at
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return {
        "success": True,
        "user": {
            "user_id": user["user_id"],
            "created_at": user["created_at"]
        }
    }


# =========================================================
# Logout
# =========================================================

@app.post("/api/auth/logout")
def logout(
    authorization: Optional[str] = Header(default=None)
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization required"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization"
        )

    token = authorization.replace("Bearer ", "", 1).strip()
    token_hash = hash_text(token)

    conn = get_db()

    conn.execute(
        """
        DELETE FROM sessions
        WHERE token_hash = ?
        """,
        (token_hash,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Logout successful"
    }


# =========================================================
# Get Chat History
# =========================================================

@app.get("/api/chat/history")
def chat_history(
    authorization: Optional[str] = Header(default=None)
):

    user_id = authenticate(authorization)

    conn = get_db()

    rows = conn.execute(
        """
        SELECT role, content, created_at
        FROM messages
        WHERE user_id = ?
        ORDER BY id ASC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    messages = []

    for row in rows:
        messages.append({
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"]
        })

    return {
        "success": True,
        "count": len(messages),
        "messages": messages
    }


# =========================================================
# Delete Chat History
# =========================================================

@app.delete("/api/chat/history")
def delete_chat_history(
    authorization: Optional[str] = Header(default=None)
):

    user_id = authenticate(authorization)

    conn = get_db()

    conn.execute(
        """
        DELETE FROM messages
        WHERE user_id = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Chat history deleted"
    }


# =========================================================
# AI Request
# =========================================================

def ask_ai(message: str, history: list):

    if not AI_API_KEY:
        return (
            "کلید API هوش مصنوعی هنوز روی سرور تنظیم نشده است. "
            "در Railway از بخش Variables مقدار AI_API_KEY را تنظیم کنید."
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are Ocean AI, a helpful and professional AI assistant. "
                "Answer clearly and accurately. "
                "If the user writes Persian, answer in Persian."
            )
        }
    ]

    for item in history:
        messages.append({
            "role": item["role"],
            "content": item["content"]
        })

    messages.append({
        "role": "user",
        "content": message
    })

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.7
    }

    try:

        response = requests.post(
            AI_API_URL,
            headers=headers,
            json=payload,
            timeout=90
        )

    except requests.RequestException as e:

        raise HTTPException(
            status_code=502,
            detail=f"AI provider connection failed: {str(e)}"
        )

    if response.status_code >= 400:

        try:
            error_data = response.json()
        except Exception:
            error_data = response.text

        raise HTTPException(
            status_code=502,
            detail={
                "message": "AI provider returned an error",
                "provider_response": error_data
            }
        )

    try:
        data = response.json()
    except Exception:

        raise HTTPException(
            status_code=502,
            detail="Invalid response from AI provider"
        )

    try:
        answer = data["choices"][0]["message"]["content"]
    except Exception:

        raise HTTPException(
            status_code=502,
            detail={
                "message": "Could not read AI response",
                "response": data
            }
        )

    return answer


# =========================================================
# Chat
# =========================================================

@app.post("/api/chat")
def chat(
    data: ChatRequest,
    authorization: Optional[str] = Header(default=None)
):

    user_id = authenticate(authorization)

    message = data.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    if len(message) > 10000:
        raise HTTPException(
            status_code=400,
            detail="Message is too long"
        )

    conn = get_db()

    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    history = []

    for row in reversed(rows):
        history.append({
            "role": row["role"],
            "content": row["content"]
        })

    save_message(
        user_id,
        "user",
        message
    )

    try:

        answer = ask_ai(
            message,
            history
        )

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"AI error: {str(e)}"
        )

    save_message(
        user_id,
        "assistant",
        answer
    )

    return {
        "success": True,
        "user_id": user_id,
        "answer": answer,
        "model": AI_MODEL,
        "created_at": now_iso()
    }


# =========================================================
# Statistics
# =========================================================

@app.get("/api/stats")
def stats(
    authorization: Optional[str] = Header(default=None)
):

    user_id = authenticate(authorization)

    conn = get_db()

    message_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM messages
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    conn.close()

    return {
        "success": True,
        "user_id": user_id,
        "messages": message_count,
        "ai_configured": bool(AI_API_KEY),
        "server": APP_NAME
    }


# =========================================================
# Server Information
# =========================================================

@app.get("/api/info")
def info():

    return {
        "success": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "backend": "FastAPI",
        "database": "SQLite",
        "status": "online",
        "ai_configured": bool(AI_API_KEY)
    }


# =========================================================
# Cleanup
# =========================================================

@app.post("/api/system/cleanup")
def cleanup():

    conn = get_db()

    # حذف sessionهای قدیمی‌تر از 30 روز
    conn.execute(
        """
        DELETE FROM sessions
        WHERE created_at < datetime('now', '-30 days')
        """
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Cleanup completed"
    }


# =========================================================
# Railway / Local Start
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000"
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
)
