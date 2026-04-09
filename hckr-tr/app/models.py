import sqlite3
import os
from datetime import datetime
import hashlib
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '../data', 'users.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создаёт все таблицы при первом запуске."""
    conn = get_db()
    c = conn.cursor()

    # --- Пользователи ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            is_admin    INTEGER DEFAULT 0,
            balance     INTEGER DEFAULT 500,
            xp          INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now')),
            last_login  TEXT,
            last_bonus_date TEXT
        )
    ''')

    # --- Прогресс по уровням ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            category    TEXT    NOT NULL,  -- 'sql' / 'xss' / 'csrf'
            level_id    INTEGER NOT NULL,
            completed   INTEGER DEFAULT 0,
            unlocked    INTEGER DEFAULT 0,
            hint_bought INTEGER DEFAULT 0,
            attempts    INTEGER DEFAULT 0,
            completed_at TEXT,
            UNIQUE(user_id, category, level_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # --- Лог каждой попытки ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            category    TEXT    NOT NULL,
            level_id    INTEGER NOT NULL,
            success     INTEGER NOT NULL,
            payload     TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Пароли
# ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def check_password(password: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(":")
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except Exception:
        return False


# ──────────────────────────────────────────────
# Пользователи
# ──────────────────────────────────────────────

def create_user(username: str, email: str, password: str) -> dict:
    """Регистрирует нового пользователя. Возвращает {'ok': True} или {'error': '...'}"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username.strip(), email.strip().lower(), hash_password(password))
        )
        conn.commit()
        return {"ok": True, "user_id": c.lastrowid}
    except sqlite3.IntegrityError as e:
        if "username" in str(e):
            return {"error": "Имя пользователя уже занято"}
        if "email" in str(e):
            return {"error": "Email уже зарегистрирован"}
        return {"error": str(e)}
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id: int):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def update_last_login(user_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Баланс / XP
# ──────────────────────────────────────────────

def add_reward(user_id: int, xp: int = 0, balance: int = 0):
    conn = get_db()
    conn.execute(
        "UPDATE users SET xp = xp + ?, balance = balance + ? WHERE id = ?",
        (xp, balance, user_id)
    )
    conn.commit()
    conn.close()


def deduct_balance(user_id: int, amount: int) -> bool:
    conn = get_db()
    user = conn.execute("SELECT balance FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or user["balance"] < amount:
        conn.close()
        return False
    conn.execute(
        "UPDATE users SET balance = balance - ? WHERE id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()
    return True


def check_and_give_daily_bonus(user_id: int):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    user = conn.execute(
        "SELECT last_bonus_date FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user and user["last_bonus_date"] != today:
        conn.execute(
            "UPDATE users SET balance = balance + 100, last_bonus_date = ? WHERE id = ?",
            (today, user_id)
        )
        conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Прогресс
# ──────────────────────────────────────────────

def _ensure_progress(c, user_id, category, level_id):
    c.execute(
        "INSERT OR IGNORE INTO progress (user_id, category, level_id) VALUES (?, ?, ?)",
        (user_id, category, level_id)
    )


def is_completed(user_id: int, category: str, level_id: int) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT completed FROM progress WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    ).fetchone()
    conn.close()
    return bool(row and row["completed"])


def is_unlocked(user_id: int, category: str, level_id: int) -> bool:
    if level_id == 1:
        return True
    conn = get_db()
    # разблокирован если предыдущий пройден ИЛИ куплен
    prev = conn.execute(
        "SELECT completed FROM progress WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id - 1)
    ).fetchone()
    bought = conn.execute(
        "SELECT unlocked FROM progress WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    ).fetchone()
    conn.close()
    return bool((prev and prev["completed"]) or (bought and bought["unlocked"]))


def mark_completed(user_id: int, category: str, level_id: int):
    conn = get_db()
    c = conn.cursor()
    _ensure_progress(c, user_id, category, level_id)
    c.execute(
        "UPDATE progress SET completed=1, completed_at=? WHERE user_id=? AND category=? AND level_id=?",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id, category, level_id)
    )
    conn.commit()
    conn.close()


def mark_unlocked(user_id: int, category: str, level_id: int):
    conn = get_db()
    c = conn.cursor()
    _ensure_progress(c, user_id, category, level_id)
    c.execute(
        "UPDATE progress SET unlocked=1 WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    )
    conn.commit()
    conn.close()


def has_hint(user_id: int, category: str, level_id: int) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT hint_bought FROM progress WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    ).fetchone()
    conn.close()
    return bool(row and row["hint_bought"])


def mark_hint_bought(user_id: int, category: str, level_id: int):
    conn = get_db()
    c = conn.cursor()
    _ensure_progress(c, user_id, category, level_id)
    c.execute(
        "UPDATE progress SET hint_bought=1 WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    )
    conn.commit()
    conn.close()


def log_attempt(user_id: int, category: str, level_id: int, success: bool, payload: str = ""):
    conn = get_db()
    c = conn.cursor()
    # увеличиваем счётчик попыток
    _ensure_progress(c, user_id, category, level_id)
    c.execute(
        "UPDATE progress SET attempts = attempts + 1 WHERE user_id=? AND category=? AND level_id=?",
        (user_id, category, level_id)
    )
    c.execute(
        "INSERT INTO attempts (user_id, category, level_id, success, payload) VALUES (?,?,?,?,?)",
        (user_id, category, level_id, int(success), payload[:500])
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Ранги
# ──────────────────────────────────────────────

RANKS = [
    (0,    "Newbie",       "⬜"),
    (150,  "Script Kiddie","🟩"),
    (500,  "White Hat",    "🟦"),
    (1000, "Elite Hacker", "🟪"),
    (2000, "Zero Day",     "🟥"),
]

def get_rank(xp: int) -> dict:
    rank_name, rank_icon = RANKS[0][1], RANKS[0][2]
    next_xp = RANKS[1][0]
    for i, (threshold, name, icon) in enumerate(RANKS):
        if xp >= threshold:
            rank_name, rank_icon = name, icon
            next_xp = RANKS[i + 1][0] if i + 1 < len(RANKS) else None
    progress_pct = 0
    if next_xp:
        # найдём порог текущего ранга
        curr_threshold = 0
        for threshold, name, _ in RANKS:
            if name == rank_name:
                curr_threshold = threshold
        span = next_xp - curr_threshold
        progress_pct = min(100, int((xp - curr_threshold) / span * 100))
    return {
        "name": rank_name,
        "icon": rank_icon,
        "next_xp": next_xp,
        "progress_pct": progress_pct,
    }


# ──────────────────────────────────────────────
# Лидерборд
# ──────────────────────────────────────────────

def get_leaderboard(limit: int = 10) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT username, xp, balance FROM users ORDER BY xp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────
# Статистика (для профиля)
# ──────────────────────────────────────────────

def get_user_stats(user_id: int) -> dict:
    conn = get_db()
    total_completed = conn.execute(
        "SELECT COUNT(*) as cnt FROM progress WHERE user_id=? AND completed=1", (user_id,)
    ).fetchone()["cnt"]

    total_attempts = conn.execute(
        "SELECT SUM(attempts) as s FROM progress WHERE user_id=?", (user_id,)
    ).fetchone()["s"] or 0

    last_activity = conn.execute(
        "SELECT MAX(created_at) as la FROM attempts WHERE user_id=?", (user_id,)
    ).fetchone()["la"]

    conn.close()
    return {
        "total_completed": total_completed,
        "total_attempts": total_attempts,
        "last_activity": last_activity,
    }