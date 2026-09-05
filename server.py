from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3, os, secrets

DB = "income_app.db"
app = FastAPI(title="Daramadza API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c=db()
    c.executescript("""
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
      UNIQUE(user_id,task_id)
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
    if c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
        c.executemany("INSERT INTO tasks(title,description,link,reward,icon) VALUES(?,?,?,?,?)",[
          ("عضویت در کانال","وارد لینک شوید و مأموریت را طبق توضیحات انجام دهید.","https://example.com/channel",5000,"📢"),
          ("ثبت نظر","صفحه معرفی‌شده را مشاهده و نظر واقعی خود را ثبت کنید.","https://example.com/page",8000,"⭐"),
          ("نظرسنجی کوتاه","به چند سؤال نظرسنجی پاسخ دهید.","https://example.com/survey",10000,"📝"),
        ])
    if c.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0:
        c.execute("INSERT INTO notices(title,body) VALUES(?,?)",("به درآمدزا خوش آمدید","مأموریت‌های جدید به‌صورت دوره‌ای در برنامه قرار می‌گیرند."))
    c.commit();c.close()
init_db()

class User(BaseModel):
    id: Optional[str]=None
    name: str="کاربر"
    phone: str=""
    balance: int=0
    invites: int=0

class Task(BaseModel):
    title: str
    description: str=""
    link: str=""
    reward: int=0
    icon: str="🎯"

class Withdrawal(BaseModel):
    user_id: str
    amount: int

class Support(BaseModel):
    user_id: str
    subject: str="پشتیبانی"
    message: str

class Notice(BaseModel):
    title: str
    body: str

@app.get("/", response_class=HTMLResponse)
def root():
    path=os.path.join(os.path.dirname(__file__),"index.html")
    if os.path.exists(path): return open(path,encoding="utf-8").read()
    return "<h2>index.html کنار server.py قرار دهید.</h2>"

@app.post("/api/users")
def save_user(u:User):
    uid=u.id or secrets.token_hex(8)
    c=db()
    old=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if old:
        c.execute("UPDATE users SET name=?,phone=? WHERE id=?",(u.name,u.phone,uid))
    else:
        c.execute("INSERT INTO users(id,name,phone,balance,invites) VALUES(?,?,?,?,?)",(uid,u.name,u.phone,0,0))
    c.commit()
    row=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone();c.close()
    return dict(row)

@app.get("/api/users")
def users():
    c=db(); rows=c.execute("SELECT * FROM users ORDER BY rowid DESC").fetchall();c.close()
    return {"users":[dict(x) for x in rows]}

@app.get("/api/users/{user_id}")
def user(user_id:str):
    c=db();row=c.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone();c.close()
    if not row: raise HTTPException(404,"کاربر پیدا نشد")
    return dict(row)

@app.get("/api/tasks")
def tasks():
    c=db();rows=c.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id DESC").fetchall();c.close()
    return {"tasks":[dict(x) for x in rows]}

@app.post("/api/tasks")
def add_task(t:Task):
    c=db();cur=c.execute("INSERT INTO tasks(title,description,link,reward,icon) VALUES(?,?,?,?,?)",(t.title,t.description,t.link,t.reward,t.icon));c.commit()
    row=c.execute("SELECT * FROM tasks WHERE id=?",(cur.lastrowid,)).fetchone();c.close();return dict(row)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id:int):
    c=db();c.execute("UPDATE tasks SET active=0 WHERE id=?",(task_id,));c.commit();c.close();return {"ok":True}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id:int, data:dict):
    uid=data.get("user_id")
    c=db()
    task=c.execute("SELECT * FROM tasks WHERE id=? AND active=1",(task_id,)).fetchone()
    if not task: raise HTTPException(404,"مأموریت پیدا نشد")
    try:
        c.execute("INSERT INTO completed(user_id,task_id) VALUES(?,?)",(uid,task_id))
    except sqlite3.IntegrityError:
        raise HTTPException(400,"این مأموریت قبلاً انجام شده است")
    c.execute("UPDATE users SET balance=balance+? WHERE id=?",(task["reward"],uid))
    c.commit();row=c.execute("SELECT balance FROM users WHERE id=?",(uid,)).fetchone();c.close()
    return {"ok":True,"balance":row["balance"]}

@app.post("/api/withdrawals")
def withdrawal(w:Withdrawal):
    if w.amount<=0: raise HTTPException(400,"مبلغ نامعتبر")
    c=db();u=c.execute("SELECT balance FROM users WHERE id=?",(w.user_id,)).fetchone()
    if not u: raise HTTPException(404,"کاربر پیدا نشد")
    if w.amount>u["balance"]: raise HTTPException(400,"موجودی کافی نیست")
    c.execute("UPDATE users SET balance=balance-? WHERE id=?",(w.amount,w.user_id))
    c.execute("INSERT INTO withdrawals(user_id,amount) VALUES(?,?)",(w.user_id,w.amount))
    c.commit();b=c.execute("SELECT balance FROM users WHERE id=?",(w.user_id,)).fetchone()["balance"];c.close()
    return {"ok":True,"balance":b}

@app.get("/api/withdrawals")
def withdrawals():
    c=db();rows=c.execute("SELECT * FROM withdrawals ORDER BY id DESC").fetchall();c.close();return {"withdrawals":[dict(x) for x in rows]}

@app.post("/api/support")
def support(s:Support):
    c=db();cur=c.execute("INSERT INTO support(user_id,subject,message) VALUES(?,?,?)",(s.user_id,s.subject,s.message));c.commit()
    row=c.execute("SELECT * FROM support WHERE id=?",(cur.lastrowid,)).fetchone();c.close();return dict(row)

@app.get("/api/support/{user_id}")
def support_user(user_id:str):
    c=db();rows=c.execute("SELECT * FROM support WHERE user_id=? ORDER BY id DESC",(user_id,)).fetchall();c.close();return {"messages":[dict(x) for x in rows]}

@app.get("/api/support")
def all_support():
    c=db();rows=c.execute("SELECT * FROM support ORDER BY id DESC").fetchall();c.close();return {"messages":[dict(x) for x in rows]}

@app.post("/api/notices")
def add_notice(n:Notice):
    c=db();cur=c.execute("INSERT INTO notices(title,body) VALUES(?,?)",(n.title,n.body));c.commit()
    row=c.execute("SELECT * FROM notices WHERE id=?",(cur.lastrowid,)).fetchone();c.close();return dict(row)

@app.get("/api/notices")
def notices():
    c=db();rows=c.execute("SELECT * FROM notices WHERE active=1 ORDER BY id DESC").fetchall();c.close();return {"notices":[dict(x) for x in rows]}

@app.get("/api/admin/summary")
def summary():
    c=db()
    result={
      "users":c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
      "tasks":c.execute("SELECT COUNT(*) FROM tasks WHERE active=1").fetchone()[0],
      "withdrawals":c.execute("SELECT COUNT(*) FROM withdrawals").fetchone()[0],
      "support":c.execute("SELECT COUNT(*) FROM support WHERE status='pending'").fetchone()[0],
    }
    c.close();return result

if __name__=="__main__":
    import uvicorn
    uvicorn.run("server:app",host="0.0.0.0",port=8000,reload=False)
