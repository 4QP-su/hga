from flask import Blueprint, render_template, request, session, redirect, url_for
from app.models import (
    get_user_by_id, get_rank, get_leaderboard,
    get_user_stats, is_completed, check_and_give_daily_bonus, get_db,
)
from app.config import SUPPORTED_LANGS
from .utils import login_required, current_user

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def index():
    user = current_user()
    uid  = user['id']

    check_and_give_daily_bonus(uid)

    # Защита от отрицательного баланса
    if user['balance'] < 0:
        conn = get_db()
        conn.execute("UPDATE users SET balance = 50 WHERE id = ? AND balance < 0", (uid,))
        conn.commit()
        conn.close()

    sql_done  = sum(1 for i in range(1, 7) if is_completed(uid, 'sql',  i))
    xss_done  = sum(1 for i in range(1, 6) if is_completed(uid, 'xss',  i))
    csrf_done = sum(1 for i in range(1, 4) if is_completed(uid, 'csrf', i))
    path_done = sum(1 for i in range(1, 4) if is_completed(uid, 'path', i))
    auth_done = sum(1 for i in range(1, 4) if is_completed(uid, 'auth', i))

    return render_template(
        'index.html',
        sql_done=sql_done, xss_done=xss_done,
        csrf_done=csrf_done, path_done=path_done, auth_done=auth_done,
    )


@main_bp.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in SUPPORTED_LANGS:
        session['lang'] = lang
    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/profile')
@login_required
def profile():
    user  = current_user()
    rank  = get_rank(user['xp'])
    stats = get_user_stats(user['id'])
    return render_template('profile.html', user=user, rank=rank, stats=stats)


@main_bp.route('/leaderboard')
@login_required
def leaderboard():
    user  = current_user()
    board = get_leaderboard(10)
    for row in board:
        row['rank_info'] = get_rank(row['xp'])
        row['is_me']     = (row['username'] == user['username'])
    return render_template('leaderboard.html', board=board)


@main_bp.route('/achievements')
@login_required
def achievements():
    user = current_user()
    uid  = user['id']
    progress = {
        'sql_master':  is_completed(uid, 'sql', 1) and is_completed(uid, 'sql', 2),
        'xss_pro':     is_completed(uid, 'xss', 1),
        'rich_kid':    user['balance'] >= 1000,
        'sql_legend':  all(is_completed(uid, 'sql', i) for i in range(1, 7)),
        'xss_legend':  all(is_completed(uid, 'xss', i) for i in range(1, 6)),
        'csrf_done':   all(is_completed(uid, 'csrf', i) for i in range(1, 4)),
        'path_done':   all(is_completed(uid, 'path', i) for i in range(1, 4)),
        'auth_done':   all(is_completed(uid, 'auth', i) for i in range(1, 4)),
        'completionist': all(
            is_completed(uid, cat, i)
            for cat, total in [('sql',6),('xss',5),('csrf',3),('path',3),('auth',3)]
            for i in range(1, total+1)
        ),
    }
    return render_template('achievements.html', progress=progress)


@main_bp.route('/reset')
def reset():
    session.clear()
    return redirect(url_for('auth.login'))