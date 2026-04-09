import re
from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models import (
    is_completed, is_unlocked, mark_completed,
    has_hint, log_attempt, add_reward,
)
from app.config import load_levels
from .utils import login_required, current_user

path_bp = Blueprint('path', __name__)


def _get_levels():
    return load_levels('levels_path_traversal.json', session.get('lang', 'ru'))


FAKE_FS = {
    'etc/passwd':         'root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin\nwww-data:x:33:33:www-data:/var/www\nhacklab:x:1000:1000:HackLab User:/home/hacklab',
    'etc/shadow':         'root:$6$rounds=656000$salt$hashedpassword:18000:0:99999:7:::\nhacklab:$6$rounds=656000$anothersalt$anotherhash:18500:0:99999:7:::',
    'var/log/app.log':    '[2026-04-01 12:00:01] INFO  Server started on port 5000\n[2026-04-01 12:01:33] INFO  User admin logged in\n[2026-04-01 12:05:17] ERROR Failed login attempt for user root\n[2026-04-01 12:10:44] INFO  Database backup completed',
    'var/log/access.log': '127.0.0.1 - admin [01/Apr/2026:12:01:33] "GET /dashboard HTTP/1.1" 200\n192.168.1.5 - - [01/Apr/2026:12:03:12] "GET /login HTTP/1.1" 200\n10.0.0.1 - - [01/Apr/2026:12:05:17] "POST /login HTTP/1.1" 401',
    'config.py':          'SECRET_KEY = "hacklab_super_secret_2026_do_not_share"\nDB_URI = "sqlite:///users.db"\nDEBUG = False\nADMIN_PASSWORD = "Adm1n@HackLab2026"',
    '.env':               'SECRET_KEY=hacklab_super_secret_2026\nDATABASE_URL=sqlite:///users.db\nADMIN_TOKEN=eyJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ.\nSMTP_PASSWORD=mailpass123',
    'home/hacklab/.ssh/id_rsa': '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA2a2rwplBQLF29amygykEMmYz0+Kcj3bKBp...\n[PRIVATE KEY CONTENT]\n-----END RSA PRIVATE KEY-----',
}


def resolve_fake_path(user_input):
    """Нормализует путь и проверяет что он в FAKE_FS."""
    # Убираем ведущий /
    path = user_input.lstrip('/')
    # Разбиваем по / и обрабатываем ..
    parts = []
    for part in re.split(r'[\\/]', path):
        if part == '..':
            if parts:
                parts.pop()
        elif part and part != '.':
            parts.append(part)
    return '/'.join(parts)


@path_bp.route('/PATH/<int:level_id>/theory')
@login_required
def path_theory(level_id):
    levels = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('path.path_labs'))
    return render_template('path_theory.html', level=level_id, level_data=level_data)


@path_bp.route('/verify-theory/path', methods=['POST'])
@login_required
def verify_path_theory():
    if all(request.form.get(f'q{i}') == 'corr' for i in range(1, 7)):
        session['path_theory_passed'] = True
        return redirect(url_for('path.path_labs'))
    lang = session.get('lang', 'ru')
    from config import t_for_lang
    err = t_for_lang(lang).get('theory_quiz_error', 'ACCESS_DENIED')
    return render_template('path_theory.html', error=err)


@path_bp.route('/PATH')
@login_required
def path_labs():
    levels = _get_levels()
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'path', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'path', lid - 1) or is_unlocked(uid, 'path', lid)
    return render_template('path_levels.html', levels=levels.values())


@path_bp.route('/PATH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def path_level(level_id):
    if not session.get('path_theory_passed'):
        return redirect(url_for('path.path_theory', level_id=level_id))

    levels     = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('path.path_labs'))

    user    = current_user()
    uid     = user['id']
    unlocked = level_id == 1 or is_completed(uid, 'path', level_id - 1) or is_unlocked(uid, 'path', level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='path')

    already     = is_completed(uid, 'path', level_id)
    hint_bought = has_hint(uid, 'path', level_id)
    message     = ""
    is_won      = False
    file_content = None
    target_file  = ""

    # Цели для каждого уровня
    targets = {1: 'etc/passwd', 2: 'var/log/app.log', 3: '.env'}
    target_file = targets.get(level_id, 'etc/passwd')

    if request.method == 'POST':
        user_path = request.form.get('filepath', '').strip()

        # ── LVL 1: простой ../ — нет фильтра ──
        if level_id == 1:
            resolved = resolve_fake_path(user_path)
            if resolved in FAKE_FS:
                file_content = FAKE_FS[resolved]
                if resolved == target_file:
                    is_won = True

        # ── LVL 2: фильтр блокирует ../ в явном виде ──
        elif level_id == 2:
            # Блокируем прямой ../ но пропускаем URL-encoded
            if '../' in user_path or '..\\' in user_path:
                message = "BLOCKED: Обнаружен path traversal. Доступ запрещён."
            else:
                # URL decode вручную
                decoded = user_path.replace('%2F', '/').replace('%2f', '/')
                decoded = decoded.replace('%5C', '\\').replace('%5c', '\\')
                # Обработка ....//
                decoded = decoded.replace('..../', '../').replace('....\\', '..\\')
                resolved = resolve_fake_path(decoded)
                if resolved in FAKE_FS:
                    file_content = FAKE_FS[resolved]
                    if resolved == target_file:
                        is_won = True

        # ── LVL 3: нужно найти config/.env ──
        elif level_id == 3:
            # Убираем только ../ но оставляем encoded
            filtered = re.sub(r'\.\.[/\\]', '', user_path)
            # Принимаем encoded версии
            decoded = filtered.replace('%2F', '/').replace('%2f', '/')
            decoded = decoded.replace('%2e%2e', '..').replace('%2E%2E', '..')
            resolved = resolve_fake_path(decoded)
            if resolved in FAKE_FS:
                file_content = FAKE_FS[resolved]
                if resolved in ('config.py', '.env'):
                    is_won = True

        log_attempt(uid, 'path', level_id, is_won, user_path)

        if is_won and not already:
            mark_completed(uid, 'path', level_id)
            add_reward(uid, xp=120, balance=200)
            message = "✅ FILE READ SUCCESS!"
        elif not is_won and not file_content and not message:
            message = "❌ Файл не найден. Попробуй другой путь."

    return render_template(
        'path.html',
        level=level_id,
        level_data=level_data,
        message=message,
        hint_bought=hint_bought,
        is_already_completed=already or is_won,
        is_won=is_won,
        file_content=file_content,
        target_file=target_file,
    )
