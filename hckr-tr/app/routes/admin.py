from flask import Blueprint, render_template, session, redirect
from app.models import get_db, add_reward
from .utils import login_required, current_user

admin_bp = Blueprint('admin', __name__)

_ADMIN_URL = '/internal/system/console/v2'

_TEXTS = {
    'ru': {
        'title':      'ПАНЕЛЬ_УПРАВЛЕНИЯ_СИСТЕМОЙ',
        'users_list': 'ИДЕНТИФИЦИРОВАННЫЕ_ПОЛЬЗОВАТЕЛИ',
        'stats':      'АНАЛИЗ_АКТИВНОСТИ_УРОВНЕЙ',
        'feed':       'ЖИВОЙ_ЛОГ_АТАК',
    },
    'kz': {
        'title':      'ЖҮЙЕНІ_БАСҚАРУ_ПАНЕЛІ',
        'users_list': 'АНЫҚТАЛҒАН_ПАЙДАЛАНУШЫЛАР',
        'stats':      'ДЕҢГЕЙЛЕРДІҢ_СТАТИСТИКАСЫ',
        'feed':       'ЖАНДЫ_ШАБУЫЛ_ТАСПАСЫ',
    },
    'en': {
        'title':      'SYSTEM_CONTROL_PANEL',
        'users_list': 'IDENTIFIED_USERS',
        'stats':      'LEVEL_ACTIVITY_ANALYSIS',
        'feed':       'LIVE_ATTACK_FEED',
    },
}


def _admin_check():
    user = current_user()
    if not user or not user['is_admin']:
        return None
    return user


@admin_bp.route(_ADMIN_URL)
@login_required
def admin_panel():
    user = _admin_check()
    if not user:
        return "404 Not Found", 404

    lang = session.get('lang', 'ru')
    t    = _TEXTS.get(lang, _TEXTS['en'])
    conn = get_db()

    users = conn.execute(
        "SELECT id, username, email, xp, balance, created_at, last_login, is_admin "
        "FROM users ORDER BY xp DESC"
    ).fetchall()

    stats = conn.execute(
        """SELECT category, level_id,
                  COUNT(*) as total_attempts,
                  SUM(success) as successes,
                  ROUND(100.0 * SUM(success) / COUNT(*), 1) as success_rate
           FROM attempts
           GROUP BY category, level_id
           ORDER BY category, level_id"""
    ).fetchall()

    recent_attempts = conn.execute(
        """SELECT a.*, u.username
           FROM attempts a JOIN users u ON a.user_id = u.id
           ORDER BY a.created_at DESC LIMIT 15"""
    ).fetchall()

    conn.close()
    return render_template(
        'admin.html',
        users=users, stats=stats, recent_attempts=recent_attempts,
        t=t, curr_lang=lang,
    )


@admin_bp.route('/admin/ban/<int:user_id>', methods=['POST'])
@login_required
def admin_ban(user_id):
    user = _admin_check()
    if not user:
        return "404 Not Found", 404
    if user['id'] == user_id:
        return "Cannot ban yourself", 400
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(_ADMIN_URL)


@admin_bp.route('/admin/give_money/<int:user_id>', methods=['POST'])
@login_required
def admin_give_money(user_id):
    if not _admin_check():
        return "404 Not Found", 404
    add_reward(user_id, xp=0, balance=100)
    return redirect(_ADMIN_URL)
