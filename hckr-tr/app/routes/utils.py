from functools import wraps
from flask import session, redirect, url_for, flash
from app.models import get_user_by_id
import sqlite3, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'data', 'users.db')


def current_user():
    uid = session.get('user_id')
    return get_user_by_id(uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash("Сначала войдите в систему", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user['is_admin']:
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return wrapper


def get_db_for_level(level_id: int):
    """Создаёт временную таблицу для SQL-уровня."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    tbl  = f"users_lvl_{level_id}"
    c.execute(f'DROP TABLE IF EXISTS {tbl}')
    c.execute(f'''CREATE TABLE {tbl}
                  (id INTEGER PRIMARY KEY, username TEXT, password TEXT, secret_data TEXT)''')
    c.execute(f"INSERT INTO {tbl} (username, password, secret_data) VALUES (?, ?, ?)",
              ('admin', 'pass123', f'FLAG{{SQL_LVL_{level_id}_DONE}}'))
    conn.commit()
    return conn, tbl
