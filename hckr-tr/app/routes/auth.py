from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app.models import (
    create_user, get_user_by_username, check_password,
    update_last_login, check_and_give_daily_bonus,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm', '').strip()

        if not username or not email or not password:
            flash("Заполните все поля", "error")
        elif len(username) < 3:
            flash("Имя пользователя: минимум 3 символа", "error")
        elif len(password) < 6:
            flash("Пароль: минимум 6 символов", "error")
        elif password != confirm:
            flash("Пароли не совпадают", "error")
        else:
            result = create_user(username, email, password)
            if result.get("ok"):
                flash("Аккаунт создан! Войдите в систему.", "success")
                return redirect(url_for('auth.login'))
            else:
                flash(result.get("error", "Ошибка регистрации"), "error")

    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user     = get_user_by_username(username)

        if user and check_password(password, user['password']):
            session.clear()
            session['user_id'] = user['id']
            session['lang']    = session.get('lang', 'ru')
            update_last_login(user['id'])
            check_and_give_daily_bonus(user['id'])
            return redirect(url_for('main.index'))
        else:
            flash("Неверный логин или пароль", "error")

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))