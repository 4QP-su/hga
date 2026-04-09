from flask import Blueprint, render_template, request, session
from app.utils.auth_utils import login_required, current_user
from app.utils.i18n import get_t
# import sqlite3 # Удаляем прямой импорт sqlite3, он должен быть в models.py или database.py

labs_bp = Blueprint('labs', __name__)

@labs_bp.route('/sql-injection/<int:lvl>', methods=['GET', 'POST'])
@login_required # Декоратор уже импортируется из utils.auth_utils
def sql_lab(lvl):
    user = current_user() # current_user() также импортируется из utils.auth_utils
    lang = session.get('lang', 'ru')
    t = get_t(lang) # get_t импортируется из utils.i18n
    
    # Твоя логика уровней (SQLmap, UNION и т.д.)
    # Здесь оставляешь свои f-строки для уязвимостей
    if lvl == 1:
        # Пример логики 1 уровня...
        pass
        
    return render_template('sql_lab.html', lvl=lvl, user=user, t=t)

# TODO: Перенести все прямые вызовы sqlite3 из этого файла в models.py или database.py
