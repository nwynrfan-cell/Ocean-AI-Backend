from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
import secrets

# =========================
# تنظیمات
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "income_app.db")

app = FastAPI(
    title="Daramadza API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Database
# =========================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        balance INTEGER DEFAULT 0,
        invites INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        link TEXT DEFAULT '',
        reward INTEGER DEFAULT 0,
        icon TEXT DEFAULT '🎯',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS completed(
        user_id TEXT,
        task_id INTEGER,
        UNIQUE(user_id, task_id)
    );

    CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        amount INTEGER,
        status TEXT DEFAULT 'pending'
    );

    CREATE TABLE IF NOT EXISTS support(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        subject TEXT,
        message TEXT,
        reply TEXT DEFAULT '',
        status TEXT DEFAULT 'pending'
    );

    CREATE TABLE IF NOT EXISTS notices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        body TEXT,
        active INTEGER DEFAULT 1
    );
    """)

    # مأموریت‌های اولیه
    task_count = conn.execute(
        "SELECT COUNT(*) FROM tasks"
    ).fetchone()[0]

    if task_count == 0:
        conn.executemany(
            """
            INSERT INTO tasks
            (title, description, link, reward, icon)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "عضویت در کانال",
                    "وارد لینک شوید و مأموریت را طبق توضیحات انجام دهید.",
                    "https://example.com/channel",
                    5000,
                    "📢"
                ),
                (
                    "ثبت نظر",
                    "صفحه معرفی‌شده را مشاهده و نظر واقعی خود را ثبت کنید.",
                    "https://example.com/page",
                    8000,
                    "⭐"
                ),
                (
                    "نظرسنجی کوتاه",
                    "به چند سؤال نظرسنجی پاسخ دهید.",
                    "https://example.com/survey",
                    10000,
                    "📝"
                )
            ]
        )

    # اطلاعیه اولیه
    notice_count = conn.execute(
        "SELECT COUNT(*) FROM notices"
    ).fetchone()[0]

    if notice_count == 0:
        conn.execute(
            """
            INSERT INTO notices(title, body)
            VALUES (?, ?)
            """,
            (
                "به درآمدزا خوش آمدید",
                "مأموریت‌های جدید به‌صورت دوره‌ای در برنامه قرار می‌گیرند."
            )
        )

    conn.commit()
    conn.close()


init_db()

# =========================
# Models
# =========================

class User(BaseModel):
    id: Optional[str] = None
    name: str = "کاربر"
    phone: str = ""
    balance: int = 0
    invites: int = 0


class Task(BaseModel):
    title: str
    description: str = ""
    link: str = ""
    reward: int = 0
    icon: str = "🎯"


class Withdrawal(BaseModel):
    user_id: str
    amount: int


class Support(BaseModel):
    user_id: str
    subject: str = "پشتیبانی"
    message: str


class Notice(BaseModel):
    title: str
    body: str


class CompleteTask(BaseModel):
    user_id: str


# =========================
# Root
# =========================

@app.get("/", response_class=HTMLResponse)
def root():
    index_path = os.path.join(BASE_DIR, "index.html")

    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()

    return """
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>درآمدزا</title>
    </head>
    <body>
        <h2>سرور درآمدزا فعال است</h2>
        <p>برای نمایش برنامه، فایل index.html را کنار main.py قرار دهید.</p>
        <p>API فعال است.</p>
    </body>
    </html>
    """


# =========================
# Health
# =========================

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "status": "online",
        "service": "Daramadza API"
    }


# =========================
# Users
# =========================

@app.post("/api/users")
def save_user(u: User):

    uid = u.id or secrets.token_hex(8)

    conn = db()

    old = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    if old:
        conn.execute(
            """
            UPDATE users
            SET name=?, phone=?
            WHERE id=?
            """,
            (u.name, u.phone, uid)
        )
    else:
        conn.execute(
            """
            INSERT INTO users
            (id, name, phone, balance, invites)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                uid,
                u.name,
                u.phone,
                0,
                0
            )
        )

    conn.commit()

    row = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    conn.close()

    return dict(row)


@app.get("/api/users")
def users():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM users
        ORDER BY rowid DESC
        """
    ).fetchall()

    conn.close()

    return {
        "users": [dict(row) for row in rows]
    }


@app.get("/api/users/{user_id}")
def get_user(user_id: str):

    conn = db()

    row = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد"
        )

    return dict(row)


# =========================
# Tasks
# =========================

@app.get("/api/tasks")
def get_tasks():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return {
        "tasks": [dict(row) for row in rows]
    }


@app.post("/api/tasks")
def add_task(task: Task):

    if task.reward < 0:
        raise HTTPException(
            status_code=400,
            detail="پاداش نمی‌تواند منفی باشد"
        )

    conn = db()

    cursor = conn.execute(
        """
        INSERT INTO tasks
        (title, description, link, reward, icon)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            task.title,
            task.description,
            task.link,
            task.reward,
            task.icon
        )
    )

    conn.commit()

    row = conn.execute(
        "SELECT * FROM tasks WHERE id=?",
        (cursor.lastrowid,)
    ).fetchone()

    conn.close()

    return dict(row)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):

    conn = db()

    cursor = conn.execute(
        """
        UPDATE tasks
        SET active=0
        WHERE id=?
        """,
        (task_id,)
    )

    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="مأموریت پیدا نشد"
        )

    return {
        "ok": True
    }


# =========================
# Complete Task
# =========================

@app.post("/api/tasks/{task_id}/complete")
def complete_task(
    task_id: int,
    data: CompleteTask
):

    user_id = data.user_id

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد"
        )

    task = conn.execute(
        """
        SELECT *
        FROM tasks
        WHERE id=? AND active=1
        """,
        (task_id,)
    ).fetchone()

    if not task:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="مأموریت پیدا نشد"
        )

    already = conn.execute(
        """
        SELECT 1
        FROM completed
        WHERE user_id=? AND task_id=?
        """,
        (user_id, task_id)
    ).fetchone()

    if already:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="این مأموریت قبلاً انجام شده است"
        )

    conn.execute(
        """
        INSERT INTO completed(user_id, task_id)
        VALUES (?, ?)
        """,
        (user_id, task_id)
    )

    conn.execute(
        """
        UPDATE users
        SET balance=balance+?
        WHERE id=?
        """,
        (task["reward"], user_id)
    )

    conn.commit()

    balance = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (user_id,)
    ).fetchone()["balance"]

    conn.close()

    return {
        "ok": True,
        "reward": task["reward"],
        "balance": balance
    }


# =========================
# Withdrawals
# =========================

@app.post("/api/withdrawals")
def create_withdrawal(w: Withdrawal):

    if w.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="مبلغ نامعتبر"
        )

    conn = db()

    user = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (w.user_id,)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد"
        )

    if w.amount > user["balance"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="موجودی کافی نیست"
        )

    conn.execute(
        """
        UPDATE users
        SET balance=balance-?
        WHERE id=?
        """,
        (w.amount, w.user_id)
    )

    cursor = conn.execute(
        """
        INSERT INTO withdrawals(user_id, amount)
        VALUES (?, ?)
        """,
        (w.user_id, w.amount)
    )

    conn.commit()

    balance = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (w.user_id,)
    ).fetchone()["balance"]

    conn.close()

    return {
        "ok": True,
        "withdrawal_id": cursor.lastrowid,
        "balance": balance
    }


@app.get("/api/withdrawals")
def get_withdrawals():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM withdrawals
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return {
        "withdrawals": [dict(row) for row in rows]
    }


# =========================
# Support
# =========================

@app.post("/api/support")
def create_support(s: Support):

    if not s.message.strip():
        raise HTTPException(
            status_code=400,
            detail="پیام خالی است"
        )

    conn = db()

    cursor = conn.execute(
        """
        INSERT INTO support
        (user_id, subject, message)
        VALUES (?, ?, ?)
        """,
        (
            s.user_id,
            s.subject,
            s.message
        )
    )

    conn.commit()

    row = conn.execute(
        """
        SELECT *
        FROM support
        WHERE id=?
        """,
        (cursor.lastrowid,)
    ).fetchone()

    conn.close()

    return dict(row)


@app.get("/api/support/{user_id}")
def get_user_support(user_id: str):

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM support
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return {
        "messages": [dict(row) for row in rows]
    }


@app.get("/api/support")
def get_all_support():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM support
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return {
        "messages": [dict(row) for row in rows]
    }


# =========================
# Notices
# =========================

@app.post("/api/notices")
def add_notice(notice: Notice):

    conn = db()

    cursor = conn.execute(
        """
        INSERT INTO notices(title, body)
        VALUES (?, ?)
        """,
        (
            notice.title,
            notice.body
        )
    )

    conn.commit()

    row = conn.execute(
        """
        SELECT *
        FROM notices
        WHERE id=?
        """,
        (cursor.lastrowid,)
    ).fetchone()

    conn.close()

    return dict(row)


@app.get("/api/notices")
def get_notices():

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM notices
        WHERE active=1
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return {
        "notices": [dict(row) for row in rows]
    }


# =========================
# Admin Summary
# =========================

@app.get("/api/admin/summary")
def admin_summary():

    conn = db()

    result = {
        "users": conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0],

        "tasks": conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE active=1"
        ).fetchone()[0],

        "withdrawals": conn.execute(
            "SELECT COUNT(*) FROM withdrawals"
        ).fetchone()[0],

        "support": conn.execute(
            """
            SELECT COUNT(*)
            FROM support
            WHERE status='pending'
            """
        ).fetchone()[0]
    }

    conn.close()

    return result


# =========================
# Railway / Local
# =========================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
)
