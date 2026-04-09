from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models import (
    is_completed, is_unlocked, mark_completed,
    has_hint, log_attempt, add_reward,
)
from app.config import load_levels
from .utils import login_required, current_user

csrf_bp = Blueprint('csrf', __name__)


def _get_levels():
    return load_levels('levels_csrf.json', session.get('lang', 'ru'))


@csrf_bp.route('/verify-theory/csrf', methods=['POST'])
@login_required
def verify_csrf_theory():
    if all(request.form.get(f'q{i}') == 'corr' for i in range(1, 7)):
        session['csrf_theory_passed'] = True
        return redirect(url_for('csrf.csrf_labs'))
    lang = session.get('lang', 'ru')
    from config import t_for_lang
    err = t_for_lang(lang).get('theory_quiz_error', 'ACCESS_DENIED')
    return render_template('csrf_theory.html', error=err)


@csrf_bp.route('/CSRF')
@login_required
def csrf_labs():
    levels = _get_levels()
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid              = lvl['id']
        lvl['completed'] = is_completed(uid, 'csrf', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'csrf', lid - 1) or is_unlocked(uid, 'csrf', lid)
    return render_template('csrf_levels.html', levels=levels.values())


@csrf_bp.route('/CSRF/<int:level_id>', methods=['GET', 'POST'])
@login_required
def csrf_level(level_id):
    if not session.get('csrf_theory_passed'):
        return redirect(url_for('csrf.csrf_theory', level_id=level_id))

    levels     = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('csrf.csrf_labs'))

    user    = current_user()
    uid     = user['id']
    unlocked = level_id == 1 or is_completed(uid, 'csrf', level_id - 1) or is_unlocked(uid, 'csrf', level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='csrf')

    already     = is_completed(uid, 'csrf', level_id)
    hint_bought = has_hint(uid, 'csrf', level_id)
    message     = ""
    is_won      = False

    if request.method == 'POST':
        action = request.form.get('action', '')

        # ── LVL 1: нажатие кнопки LAUNCH ATTACK ──
        if level_id == 1:
            if action == 'launch':
                is_won = True

        # ── LVL 2: указан правильный получатель и сумма ──
        elif level_id == 2:
            if action == 'transfer':
                is_won = True

        # ── LVL 3: GET-запрос с параметром атаки ──
        elif level_id == 3:
            evil_param = request.args.get('evil') or request.form.get('evil', '')
            if evil_param == 'attack' or action == 'get_attack':
                is_won = True

        log_attempt(uid, 'csrf', level_id, is_won, action)

        if is_won and not already:
            mark_completed(uid, 'csrf', level_id)
            add_reward(uid, xp=120, balance=200)
            message = "✅ CSRF ATTACK SUCCESS!"
        elif not is_won:
            message = "❌ Атака не удалась. Попробуй ещё раз."

    return render_template(
        'csrf.html',
        level=level_id,
        level_data=level_data,
        message=message,
        hint_bought=hint_bought,
        is_already_completed=already or is_won,
        is_won=is_won,
    )


@csrf_bp.route('/CSRF/<int:level_id>/theory')
@login_required
def csrf_theory(level_id):
    levels = _get_levels()
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('csrf.csrf_labs'))
    return render_template('csrf_theory.html', level=level_id, level_data=level_data)


@csrf_bp.route('/csrf_victim_action', methods=['GET', 'POST'])
@login_required
def csrf_victim_action():
    """Имитация уязвимого endpoint без CSRF-защиты."""
    action = request.args.get('action') or request.form.get('action', '')
    return f"ACTION_EXECUTED: {action}", 200
