import re
import json
import base64
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models import (
    is_completed, is_unlocked, mark_completed,
    has_hint, log_attempt, add_reward,
)
from app.config import load_levels
from .utils import login_required, current_user

authbypass_bp = Blueprint('authbypass', __name__)


def _get_levels():
    return load_levels('levels_auth.json', session.get('lang', 'ru'))


def make_fake_jwt(payload_dict, algorithm='HS256'):
    """Создаёт фейковый JWT токен без реальной подписи."""
    header = base64.b64encode(json.dumps({'alg': algorithm, 'typ': 'JWT'}).encode()).decode().rstrip('=')
    payload = base64.b64encode(json.dumps(payload_dict).encode()).decode().rstrip('=')
    signature = 'fake_signature_not_verified'
    return f"{header}.{payload}.{signature}"


def decode_fake_jwt(token):
    """Декодирует фейковый JWT (без проверки подписи)."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        decoded = base64.b64decode(payload)
        return json.loads(decoded)
    except:
        return None


AUTH_TARGET_PASSWORD = 'Admin2026!'
AUTH_RESET_TOKEN = base64.b64encode(b'admin_reset_token_secret_2026').decode()


@authbypass_bp.route('/AUTH/<int:level_id>/theory')
@login_required
def auth_theory(level_id):
    levels = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('authbypass.auth_labs'))
    return render_template('auth_theory.html', level=level_id, level_data=level_data)


@authbypass_bp.route('/verify-theory/auth', methods=['POST'])
@login_required
def verify_auth_theory():
    if all(request.form.get(f'q{i}') == 'corr' for i in range(1, 7)):
        session['auth_theory_passed'] = True
        return redirect(url_for('authbypass.auth_labs'))
    lang = session.get('lang', 'ru')
    from config import t_for_lang
    err = t_for_lang(lang).get('theory_quiz_error', 'ACCESS_DENIED')
    return render_template('auth_theory.html', error=err)


@authbypass_bp.route('/AUTH')
@login_required
def auth_labs():
    levels = _get_levels()
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'auth', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'auth', lid - 1) or is_unlocked(uid, 'auth', lid)
    return render_template('auth_levels.html', levels=levels.values())


@authbypass_bp.route('/AUTH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def auth_level(level_id):
    if not session.get('auth_theory_passed'):
        return redirect(url_for('authbypass.auth_theory', level_id=level_id))

    levels     = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('authbypass.auth_labs'))

    user    = current_user()
    uid     = user['id']
    unlocked = level_id == 1 or is_completed(uid, 'auth', level_id - 1) or is_unlocked(uid, 'auth', level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='auth')

    already     = is_completed(uid, 'auth', level_id)
    hint_bought = has_hint(uid, 'auth', level_id)
    message     = ""
    is_won      = False

    if request.method == 'POST':
        # ── LVL 1: Brute Force ──
        # Простой перебор пароля из списка common passwords
        if level_id == 1:
            guess = request.form.get('password', '').strip()
            common_passwords = ['password', '123456', 'admin', 'letmein', 'welcome', 'Admin2026!']
            if guess in common_passwords:
                message = f"❌ Корректный пароль найден... но это '{ guess}' из словаря. Перепробуй!"
            if guess == AUTH_TARGET_PASSWORD:
                is_won = True
                message = "✅ PASSWORD CRACKED!"

        # ── LVL 2: JWT Token Manipulation ──
        # Токен с role:admin можно самостоятельно создать
        elif level_id == 2:
            user_jwt = request.form.get('jwt_token', '').strip()
            if user_jwt:
                payload = decode_fake_jwt(user_jwt)
                if payload and payload.get('role') == 'admin':
                    is_won = True
                    message = "✅ JWT TOKEN MODIFIED!"
                elif payload:
                    message = f"❌ Invalid role. Got: {payload.get('role')}"
                else:
                    message = "❌ Invalid JWT token format."

        # ── LVL 3: Password Reset Token Prediction ──
        # Токен — это base64 кодированная строка
        elif level_id == 3:
            guess_token = request.form.get('reset_token', '').strip()
            if guess_token == AUTH_RESET_TOKEN:
                is_won = True
                message = "✅ RESET TOKEN PREDICTED!"
            elif guess_token:
                message = f"❌ Token mismatch. Try again..."

        log_attempt(uid, 'auth', level_id, is_won, request.form.get('password') or request.form.get('jwt_token') or request.form.get('reset_token'))

        if is_won and not already:
            mark_completed(uid, 'auth', level_id)
            add_reward(uid, xp=150, balance=250)
            message = "✅ LEVEL COMPLETED!"

    # Подготавливаем подсказки для показа уровня
    hints = {
        1: "Попробуй самые распространённые пароли. Подсказка: пароль содержит 'Admin' и цифру",
        2: "JWT токен состоит из трёх частей, разделённых точками. Вторая часть — это payload в base64",
        3: "Токен — это base64 кодированная строка. Может содержать слова как 'admin', 'reset', 'token'",
    }

    return render_template(
        'auth.html',
        level=level_id,
        level_data=level_data,
        message=message,
        hint_bought=hint_bought,
        is_already_completed=already or is_won,
        is_won=is_won,
        hint_text=hints.get(level_id, ''),
        common_passwords=['password', '123456', 'admin', 'letmein', 'welcome'],
        example_jwt=make_fake_jwt({'user': 'test', 'role': 'user'}),
    )
