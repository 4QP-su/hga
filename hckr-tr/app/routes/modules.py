import re, json, hashlib, base64
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.models import (
    is_completed, is_unlocked, mark_completed, mark_unlocked,
    has_hint, mark_hint_bought, log_attempt, add_reward, deduct_balance, get_db,
)
from app.config import load_levels
from .utils import login_required, current_user

modules_bp = Blueprint('modules', __name__)

# ── Маршруты до уровней ─────────────────────────────────────────
_ROUTE_MAP = {
    'sql':  ('sql.sql_level',  'sql.sql_labs'),
    'xss':  ('xss.xss_level',  'xss.xss_labs'),
    'csrf': ('modules.csrf_level', 'modules.csrf_labs'),
    'path': ('modules.path_level', 'modules.path_labs'),
    'auth': ('modules.auth_level', 'modules.auth_labs'),
}

# ── Универсальный buy_hint ───────────────────────────────────────
@modules_bp.route('/buy_hint/<category>/<int:level_id>')
@login_required
def buy_hint(category, level_id):
    if category not in _ROUTE_MAP:
        return redirect(url_for('main.index'))
    user = current_user()
    uid  = user['id']
    if not has_hint(uid, category, level_id):
        if not deduct_balance(uid, 150):
            flash("Недостаточно средств!", "warning")
        else:
            mark_hint_bought(uid, category, level_id)
    level_route, _ = _ROUTE_MAP[category]
    return redirect(url_for(level_route, level_id=level_id))


# ── Универсальный surrender ──────────────────────────────────────
@modules_bp.route('/surrender/<category>/<int:level_id>')
@login_required
def surrender(category, level_id):
    if category not in _ROUTE_MAP:
        return redirect(url_for('main.index'))
    uid = current_user()['id']
    deduct_balance(uid, 100)
    conn = get_db()
    conn.execute("UPDATE users SET balance = MAX(balance, 0) WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    _, labs_route = _ROUTE_MAP[category]
    return redirect(url_for(labs_route))


# ── Универсальный buy_level (разблокировка за деньги) ───────────
@modules_bp.route('/buy_level/<category>/<int:level_id>')
@login_required
def buy_level(category, level_id):
    if category not in _ROUTE_MAP:
        return redirect(url_for('main.index'))
    uid = current_user()['id']
    if deduct_balance(uid, 100):
        mark_unlocked(uid, category, level_id)
        level_route, _ = _ROUTE_MAP[category]
        return redirect(url_for(level_route, level_id=level_id))
    flash("Недостаточно средств!", "warning")
    _, labs_route = _ROUTE_MAP[category]
    return redirect(url_for(labs_route))


# ════════════════════════════════════════════════════════════════
# CSRF
# ════════════════════════════════════════════════════════════════

@modules_bp.route('/CSRF')
@login_required
def csrf_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_csrf.json', lang)
    uid    = current_user()['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'csrf', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid,'csrf',lid-1) or is_unlocked(uid,'csrf',lid)
    return render_template(
        'module_levels.html', levels=levels.values(),
        module_cat='csrf', module_name='CSRF', accent_color='#ff3e3e', total_levels=3,
        technique_tags=[
            {'name':'State-changing request','cls':'tag-red'},
            {'name':'Session hijack',        'cls':'tag-red'},
            {'name':'SameSite bypass',       'cls':'tag-gold'},
        ]
    )


@modules_bp.route('/CSRF/<int:level_id>', methods=['GET', 'POST'])
@login_required
def csrf_level(level_id):
    lang       = session.get('lang', 'ru')
    level_data = load_levels('levels_csrf.json', lang).get(level_id)
    if not level_data:
        return redirect(url_for('modules.csrf_labs'))

    uid      = current_user()['id']
    unlocked = level_id == 1 or is_completed(uid,'csrf',level_id-1) or is_unlocked(uid,'csrf',level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='csrf')

    already     = is_completed(uid, 'csrf', level_id)
    hint_bought = has_hint(uid, 'csrf', level_id)
    message, is_won = "", False

    if request.method == 'POST':
        action     = request.form.get('action', '')
        evil_param = request.args.get('evil') or request.form.get('evil', '')
        is_won = (
            (level_id == 1 and action == 'launch') or
            (level_id == 2 and action == 'transfer') or
            (level_id == 3 and (evil_param == 'attack' or action == 'get_attack'))
        )
        log_attempt(uid, 'csrf', level_id, is_won, action)
        if is_won and not already:
            mark_completed(uid, 'csrf', level_id)
            add_reward(uid, xp=120, balance=200)
            message = "✅ CSRF ATTACK SUCCESS!"
        elif not is_won:
            message = "❌ Атака не удалась. Попробуй ещё раз."

    return render_template(
        'module_level.html',
        level=level_id, level_data=level_data,
        module_cat='csrf', module_name='CSRF', accent_color='#ff3e3e', total_levels=3,
        message=message, hint_bought=hint_bought,
        is_already_completed=already or is_won, is_won=is_won,
    )


# ════════════════════════════════════════════════════════════════
# PATH TRAVERSAL
# ════════════════════════════════════════════════════════════════

FAKE_FS = {
    'etc/passwd':         'root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin\nwww-data:x:33:33:www-data:/var/www\nhacklab:x:1000:1000:HackLab User:/home/hacklab',
    'etc/shadow':         'root:$6$rounds=656000$salt$hashedpassword:18000:0:99999:7:::\nhacklab:$6$rounds=656000$anothersalt$anotherhash:18500:0:99999:7:::',
    'var/log/app.log':    '[2026-04-01 12:00:01] INFO  Server started on port 5000\n[2026-04-01 12:01:33] INFO  User admin logged in\n[2026-04-01 12:05:17] ERROR Failed login for user root\n[2026-04-01 12:10:44] INFO  Database backup completed',
    'var/log/access.log': '127.0.0.1 - admin [01/Apr/2026:12:01:33] "GET /dashboard HTTP/1.1" 200\n192.168.1.5 - - [01/Apr/2026:12:03:12] "GET /login HTTP/1.1" 200',
    'config.py':          'SECRET_KEY = "hacklab_super_secret_2026_do_not_share"\nDB_URI = "sqlite:///users.db"\nDEBUG = False\nADMIN_PASSWORD = "Adm1n@HackLab2026"',
    '.env':               'SECRET_KEY=hacklab_super_secret_2026\nDATABASE_URL=sqlite:///users.db\nADMIN_TOKEN=eyJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ.\nSMTP_PASSWORD=mailpass123',
    'home/hacklab/.ssh/id_rsa': '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...[PRIVATE KEY CONTENT]\n-----END RSA PRIVATE KEY-----',
}

def _resolve(raw: str) -> str:
    parts = []
    for part in re.split(r'[\\/]', raw.lstrip('/')):
        if part == '..':
            if parts: parts.pop()
        elif part and part != '.':
            parts.append(part)
    return '/'.join(parts)


@modules_bp.route('/PATH')
@login_required
def path_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_path_traversal.json', lang)
    uid    = current_user()['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'path', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid,'path',lid-1) or is_unlocked(uid,'path',lid)
    return render_template(
        'module_levels.html', levels=levels.values(),
        module_cat='path', module_name='PATH_TRAVERSAL', accent_color='#00e5ff', total_levels=3,
        technique_tags=[
            {'name':'../ escape',      'cls':'tag-cyan'},
            {'name':'URL encoding',    'cls':'tag-cyan'},
            {'name':'Config file read','cls':'tag-red'},
        ]
    )


@modules_bp.route('/PATH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def path_level(level_id):
    lang       = session.get('lang', 'ru')
    level_data = load_levels('levels_path_traversal.json', lang).get(level_id)
    if not level_data:
        return redirect(url_for('modules.path_labs'))

    uid      = current_user()['id']
    unlocked = level_id == 1 or is_completed(uid,'path',level_id-1) or is_unlocked(uid,'path',level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='path')

    already      = is_completed(uid, 'path', level_id)
    hint_bought  = has_hint(uid, 'path', level_id)
    targets      = {1: 'etc/passwd', 2: 'var/log/app.log', 3: '.env'}
    target_file  = targets.get(level_id, 'etc/passwd')
    message, is_won, file_content = "", False, None

    if request.method == 'POST':
        raw = request.form.get('filepath', '').strip()

        if level_id == 1:
            resolved = _resolve(raw)
            if resolved in FAKE_FS:
                file_content = FAKE_FS[resolved]
                is_won = (resolved == target_file)

        elif level_id == 2:
            if '../' in raw or '..\\' in raw:
                message = "BLOCKED: path traversal detected."
            else:
                decoded  = raw.replace('%2F','/').replace('%2f','/').replace('%5C','\\').replace('%5c','\\')
                decoded  = decoded.replace('..../',  '../').replace('....\\', '..\\')
                resolved = _resolve(decoded)
                if resolved in FAKE_FS:
                    file_content = FAKE_FS[resolved]
                    is_won = (resolved == target_file)

        elif level_id == 3:
            filtered = re.sub(r'\.\.[/\\]', '', raw)
            decoded  = filtered.replace('%2F','/').replace('%2f','/')
            decoded  = decoded.replace('%2e%2e','..').replace('%2E%2E','..')
            resolved = _resolve(decoded)
            if resolved in FAKE_FS:
                file_content = FAKE_FS[resolved]
                is_won = resolved in ('config.py', '.env')

        log_attempt(uid, 'path', level_id, is_won, raw)
        if is_won and not already:
            mark_completed(uid, 'path', level_id)
            add_reward(uid, xp=120, balance=200)
            message = "✅ FILE READ SUCCESS!"
        elif not is_won and not file_content and not message:
            message = "❌ Файл не найден. Попробуй другой путь."

    return render_template(
        'module_level.html',
        level=level_id, level_data=level_data,
        module_cat='path', module_name='PATH_TRAVERSAL', accent_color='#00e5ff', total_levels=3,
        message=message, hint_bought=hint_bought,
        is_already_completed=already or is_won, is_won=is_won,
        file_content=file_content, target_file=target_file,
    )


# ════════════════════════════════════════════════════════════════
# BROKEN AUTH
# ════════════════════════════════════════════════════════════════

WEAK_PASSWORDS     = ['password','123456','admin','qwerty','letmein','welcome','monkey','dragon','master','111111']
AUTH_TARGET_PWD    = 'dragon'
AUTH_RESET_TOKEN   = hashlib.md5(b'1743465600').hexdigest()

def _make_jwt(payload: dict) -> str:
    h = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b'=').decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    return f"{h}.{p}."

def _decode_jwt(token: str):
    try:
        parts = token.split('.')
        if len(parts) != 3: return None
        return json.loads(base64.urlsafe_b64decode(parts[1] + '==').decode())
    except Exception:
        return None


@modules_bp.route('/AUTH')
@login_required
def auth_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_auth.json', lang)
    uid    = current_user()['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'auth', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid,'auth',lid-1) or is_unlocked(uid,'auth',lid)
    return render_template(
        'module_levels.html', levels=levels.values(),
        module_cat='auth', module_name='BROKEN_AUTH', accent_color='#ffd700', total_levels=3,
        technique_tags=[
            {'name':'Brute force',       'cls':'tag-gold'},
            {'name':'JWT alg:none',      'cls':'tag-red'},
            {'name':'Predictable token', 'cls':'tag-gold'},
        ]
    )


@modules_bp.route('/AUTH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def auth_level(level_id):
    lang       = session.get('lang', 'ru')
    level_data = load_levels('levels_auth.json', lang).get(level_id)
    if not level_data:
        return redirect(url_for('modules.auth_labs'))

    uid      = current_user()['id']
    unlocked = level_id == 1 or is_completed(uid,'auth',level_id-1) or is_unlocked(uid,'auth',level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='auth')

    already     = is_completed(uid, 'auth', level_id)
    hint_bought = has_hint(uid, 'auth', level_id)
    message, is_won, extra = "", False, {}

    if request.method == 'POST':
        if level_id == 1:
            pw     = request.form.get('password', '').strip()
            is_won = (pw == AUTH_TARGET_PWD)
            if not is_won:
                message = f"❌ Неверный пароль: '{pw}'. Попробуй другой."

        elif level_id == 2:
            token   = request.form.get('jwt_token', '').strip()
            payload = _decode_jwt(token)
            is_won  = bool(payload and payload.get('role') == 'admin')
            if not is_won:
                role = payload.get('role','неизвестно') if payload else 'невалидный токен'
                extra['demo_token'] = _make_jwt({"username":"hacker","role":"user"})
                message = f"❌ Роль: {role}. Нужна role=admin."

        elif level_id == 3:
            token  = request.form.get('reset_token', '').strip()
            is_won = (token == AUTH_RESET_TOKEN)
            if not is_won:
                extra['hint_ts'] = 1743465600
                message = "❌ Неверный токен. Подсказка: md5(1743465600)"

        payload_str = (request.form.get('password') or
                       request.form.get('jwt_token') or
                       request.form.get('reset_token') or '')
        log_attempt(uid, 'auth', level_id, is_won, payload_str)

        if is_won and not already:
            mark_completed(uid, 'auth', level_id)
            add_reward(uid, xp=150, balance=250)
            message = "✅ AUTH BYPASS SUCCESS!"

    if level_id == 2 and 'demo_token' not in extra:
        extra['demo_token'] = _make_jwt({"username":"hacker","role":"user"})

    return render_template(
        'module_level.html',
        level=level_id, level_data=level_data,
        module_cat='auth', module_name='BROKEN_AUTH', accent_color='#ffd700', total_levels=3,
        message=message, hint_bought=hint_bought,
        is_already_completed=already or is_won, is_won=is_won,
        weak_passwords=WEAK_PASSWORDS, extra=extra,
    )
