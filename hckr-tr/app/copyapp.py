from flask import Flask, render_template, request, session, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime
import json, os, re, hashlib, base64
from flask import Flask, render_template, request, session, redirect, url_for, flash

from models import (
    init_db, create_user, get_user_by_username, get_user_by_id,
    check_password, update_last_login,
    add_reward, deduct_balance, check_and_give_daily_bonus,
    is_completed, is_unlocked, mark_completed, mark_unlocked,
    has_hint, mark_hint_bought, log_attempt,
    get_rank, get_leaderboard, get_user_stats,
)

# ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, '../templates'),
            static_folder=os.path.join(BASE_DIR, '../static'))
app.secret_key = "supersecretkey_2026"

DB_PATH = os.path.join(BASE_DIR, 'users.db')

# Инициализируем таблицы при старте
with app.app_context():
    init_db()


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────
def load_levels(filename, lang):
    """Загружает уровни из JSON файла."""
    path = os.path.join(BASE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    lang = lang if lang in all_data else 'ru'
    result = {}
    for lid_str, data in all_data[lang].items():
        lid = int(lid_str)
        data['id'] = lid
        result[lid] = data
    return result

def current_user():
    """Возвращает dict с данными пользователя или None."""
    uid = session.get('user_id')
    if not uid:
        return None
    return get_user_by_id(uid)


def login_required(f):
    """Декоратор: перенаправляет на /login если не вошёл."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash("Сначала войдите в систему", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user['is_admin']:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper


def get_db_for_level(level_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    table_name = f"users_lvl_{level_id}"
    c.execute(f'DROP TABLE IF EXISTS {table_name}')
    c.execute(f'CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, username TEXT, password TEXT, secret_data TEXT)')
    c.execute(f'INSERT INTO {table_name} (username, password, secret_data) VALUES (?, ?, ?)',
              ('admin', 'pass123', f'FLAG{{SQL_LVL_{level_id}_DONE}}'))
    conn.commit()
    return conn, table_name


# ──────────────────────────────────────────────
# СЛОВАРЬ ПЕРЕВОДОВ
# Новый язык: добавьте ключ (например 'de') с тем же набором строк, что у 'ru'.
# Контент уровней — в levels_sql.json / levels_xss.json под тем же кодом (или fallback на 'ru').
# ──────────────────────────────────────────────
translations = {
    'ru': {
        'dashboard': 'Панель управления',
        'profile': 'Профиль Хакера',
        'balance': 'Баланс',
        'xp': 'Опыт (XP)',
        'sql_title': 'SQL Инъекции',
        'sql_desc': 'Проникновение в базы данных через уязвимые поля ввода.',
        'xss_title': 'XSS Атаки',
        'xss_desc': 'Внедрение вредоносных скриптов на сторону клиента.',
        'exit': 'Выход',
        'sql_header': '[!] ТАРГЕТ_ИНФРАСТРУКТУРА_SQL',
        'sql_path': 'ПУТЬ: root/цели/уровень_',
        'sql_intel': 'РАЗВЕДДАННЫЕ: ',
        'abort_btn': 'ПРЕРВАТЬ_МИССИЮ',
        'theory_title': '> [ МОДУЛЬ_ТЕОРИИ ]',
        'outcome_title': 'ОЖИДАЕМЫЙ_РЕЗУЛЬТАТ:',
        'mission_obj': 'ЦЕЛЬ_МИССИИ',
        'auth_gate': '> ТЕСТИРОВАНИЕ_ВВОДА (QUERY_TEST)',
        'sql_stats_title': 'АНАЛИЗ_УЯЗВИМОСТИ: OWASP_TOP_10',
        'sql_stats_text': 'Инъекции стабильно входят в OWASP Top 10. Уязвимость возникает когда данные от пользователя передаются интерпретатору как часть команды.',
        'sql_global_info': 'SQL-инъекция позволяет атакующему вмешаться в запросы к базе данных.',
        'db_structure_label': 'СТРУКТУРА БАЗЫ ДАННЫХ:',
        'btn_exploit': 'ВЫПОЛНИТЬ ЗАПРОС',
        'get_hint_label': 'ПОЛУЧИТЬ ПОДСКАЗКУ (-${hint_price})',
        'hint_buy_confirm': 'Уверен? С баланса спишется ${hint_price} за подсказку.',
        'shop_hint_bracket': '[ ПОДСКАЗКА -${hint_price} ]',
        'surrender_confirm': 'Сдаться? С баланса спишется ${surrender_price}.',
        'low_balance_for_hint': '⚠ LOW_BALANCE: недостаточно средств для подсказки (${hint_price}). Ежедневный бонус +${daily_bonus} при следующем входе.',
        'flash_not_enough_for_hint': 'Недостаточно средств для подсказки. Подожди дневного бонуса.',
        'wallet_balance_line': 'БАЛАНС:',
        'hint_panel_title': '[!] ПОДСКАЗКА_РАСШИФРОВАНА',
        'surrender_btn': 'ПРИЗНАТЬ ПОРАЖЕНИЕ (-${surrender_price})',
        'start_mission_btn': '> OVERRIDE GATEWAY',
        'abort_mission_btn': '[ ОТМЕНА ОПЕРАЦИИ ]',
        'access_granted_text': 'Узел успешно взломан. Система под контролем.',
        'next_level_btn': 'ВЗЛОМАТЬ СЛЕДУЮЩИЙ УЗЕЛ',
        'return_to_hub': 'ВЕРНУТЬСЯ В ХАБ',
        'sql_win_rewards': 'Награда: +50 XP | +$125 на баланс',
        'sql_theory_html_title': 'SQL_THEORY | CORE_DATABASE',
        'sql_theory_h1': '[ МОДУЛЬ_01: SQL_ИНЪЕКЦИЯ_ТЕОРИЯ ]',
        'sql_theory_p1': '> SQL-инъекция — подмена части запроса к СУБД через пользовательский ввод, когда данные склеиваются в строку SQL без изоляции.',
        'sql_theory_p2': '> Классика: конкатенация в коде вида query = "SELECT * FROM users WHERE login = \'" + login + "\'" — внутрь login попадает живой SQL.',
        'sql_theory_p3': '> Обход логина: кавычка закрывает строку, далее OR 1=1 делает условие всегда истинным; символы комментария (--, #) отрезают хвост оригинального запроса.',
        'sql_theory_p4': '> UNION SELECT объединяет результаты двух SELECT; число и типы столбцов должны совпадать — иначе ошибка (часто подбирают через ORDER BY n).',
        'sql_theory_p5': '> В MySQL служебные представления information_schema (tables, columns) помогают узнать структуру БД без прямого доступа к файлам.',
        'sql_theory_p6': '> Blind / time-based SQLi: ответ приложения не показывает строки, но по задержкам (SLEEP) или по отличию ответа «да/нет» всё равно утечка данных.',
        'sql_theory_p7': '> Основная защита уровня приложения — параметризованные запросы (prepared statements): плейсхолдеры, отдельная передача значений, без интерполяции в текст SQL.',
        'sql_theory_p8': '> OWASP классифицирует инъекции как A03:2021 Injection; комбинируйте валидацию, принцип наименьших привилегий в БД и мониторинг аномальных запросов.',
        'sql_theory_quiz_heading': '[ КВИЗ — 6 ВОПРОСОВ. НУЖНЫ ВСЕ ВЕРНЫЕ ОТВЕТЫ ]',
        'sql_theory_submit': 'ПОДТВЕРДИТЬ ЗНАНИЯ',
        'sql_th_q1': '1/6. Что даёт добавление OR 1=1 в условие WHERE после закрытой кавычки в уязвимом запросе?',
        'sql_th_q1o1': 'Удаление таблицы без подтверждения',
        'sql_th_q1o2': 'Условие WHERE становится всегда истинным',
        'sql_th_q1o3': 'Отключение пароля root в MySQL',
        'sql_th_q2': '2/6. Какой подход лучше всего снижает риск SQLi в типичном веб-приложении?',
        'sql_th_q2o1': 'Только maxlength в HTML-форме',
        'sql_th_q2o2': 'Параметризованные запросы и привязка параметров',
        'sql_th_q2o3': 'Хранить пароли открытым текстом «для отладки»',
        'sql_th_q3': '3/6. Зачем в инъекции часто используют -- или # после payload?',
        'sql_th_q3o1': 'Чтобы «закомментировать» остаток исходного SQL',
        'sql_th_q3o2': 'Чтобы включить шифрование соединения',
        'sql_th_q3o3': 'Чтобы ускорить выполнение SELECT',
        'sql_th_q4': '4/6. Что нужно для успешного UNION SELECT между двумя запросами?',
        'sql_th_q4o1': 'Одинаковое имя базы в обоих запросах',
        'sql_th_q4o2': 'Права FILE на сервере',
        'sql_th_q4o3': 'Совместимое число (и типы) столбцов у обоих SELECT',
        'sql_th_q5': '5/6. Зачем обращаются к information_schema в контексте SQLi?',
        'sql_th_q5o1': 'Чтобы удалить служебные таблицы',
        'sql_th_q5o2': 'Чтобы отключить логирование',
        'sql_th_q5o3': 'Чтобы узнать имена таблиц и столбцов (метаданные)',
        'sql_th_q6': '6/6. Second-order SQLi — это когда…',
        'sql_th_q6o1': 'Вредоносный ввод сохраняют и он выполняется позже в другом запросе',
        'sql_th_q6o2': 'Атака возможна только без HTTPS',
        'sql_th_q6o3': 'СУБД запрещает UNION',
        # auth
        'login_title': 'Вход в систему',
        'register_title': 'Регистрация',
        'username_label': 'Имя пользователя',
        'email_label': 'Email',
        'password_label': 'Пароль',
        'login_btn': 'Войти',
        'register_btn': 'Зарегистрироваться',
        'no_account': 'Нет аккаунта?',
        'have_account': 'Уже есть аккаунт?',
        'theory_quiz_error': 'ACCESS_DENIED: неверный ответ квиза. Нужны все 6 верных ответов.',
        'xss_theory_html_title': 'XSS_THEORY | SCRIPT_INJECTION',
        'xss_theory_h1': '[ МОДУЛЬ_02: XSS_THEORY ]',
        'xss_theory_p1': '> XSS (Cross-Site Scripting) — внедрение исполняемого кода (обычно JavaScript) в страницу, которую видит другой пользователь.',
        'xss_theory_p2': '> Reflected — payload «отражается» в ответе сервера; Stored — сохраняется на сервере и показывается многим; DOM-based — ошибка в клиентском JS при разборе URL/данных.',
        'xss_theory_p3': '> Без экранирования теги и атрибуты (script, img onerror, svg onload, javascript: в href) могут привести к исполнению кода в контексте страницы.',
        'xss_theory_p4': '> HttpOnly на cookie усложняет кражу сессии через document.cookie, но не отменяет другие эффекты XSS (подмена DOM, действия от имени пользователя).',
        'xss_theory_p5': '> Content-Security-Policy ограничивает источники скриптов и снижает вероятность исполнения инлайнового JS; комбинируйте с валидацией и контекстным кодированием.',
        'xss_theory_p6': '> Контекст важен: экранирование для HTML, атрибутов, JS-строк и URL различается; одна и та же строка может быть безопасна в одном месте и опасна в другом.',
        'xss_theory_quiz_heading': '[ КВИЗ — 6 ВОПРОСОВ. НУЖНЫ ВСЕ ВЕРНЫЕ ОТВЕТЫ ]',
        'xss_theory_submit': 'ПОДТВЕРДИТЬ ЗНАНИЯ',
        'xss_theory_nav': '[ ТЕОРИЯ XSS ]',
        'xss_th_q1': '1/6. Где выполняется вредоносный JavaScript при успешной XSS?',
        'xss_th_q1o1': 'Только на сервере приложения',
        'xss_th_q1o2': 'В браузере жертвы (клиентская сторона)',
        'xss_th_q1o3': 'На DNS-сервере',
        'xss_th_q2': '2/6. Для чего в первую очередь используют Content-Security-Policy (CSP)?',
        'xss_th_q2o1': 'Чтобы ограничить, откуда браузеру разрешено загружать и выполнять скрипты',
        'xss_th_q2o2': 'Чтобы ускорить загрузку CSS',
        'xss_th_q2o3': 'Чтобы отключить HTTPS',
        'xss_th_q3': '3/6. Reflected XSS означает, что payload…',
        'xss_th_q3o1': 'Сохраняется только в cookie браузера',
        'xss_th_q3o2': 'Попадает в ответ сервера и отображается без долговременного хранения на сервере',
        'xss_th_q3o3': 'Выполняется только в cron-задаче',
        'xss_th_q4': '4/6. Может ли конструкция вида <img src=x onerror=alert(1)> привести к исполнению JS?',
        'xss_th_q4o1': 'Нет, тег img не выполняет скрипты',
        'xss_th_q4o2': 'Да, обработчик onerror может вызвать JavaScript',
        'xss_th_q4o3': 'Только если картинка существует на сервере',
        'xss_th_q5': '5/6. Достаточно ли «закодировать вывод один раз» в любом месте страницы?',
        'xss_th_q5o1': 'Да, одного алгоритма достаточно для HTML, JS и URL',
        'xss_th_q5o2': 'Нет, нужно кодирование с учётом контекста (HTML, атрибут, скрипт, URL)',
        'xss_th_q5o3': 'Нет, достаточно только maxlength',
        'xss_th_q6': '6/6. Флаг HttpOnly на cookie сессии…',
        'xss_th_q6o1': 'Полностью делает невозможной любую XSS-атаку',
        'xss_th_q6o2': 'Защищает cookie от чтения через document.cookie, но не все сценарии XSS',
        'xss_th_q6o3': 'Отключает сессии в браузере',
        'theory_title': '> [ МОДУЛЬ_ТЕОРЕТИЧЕСКОЙ_ПОДГОТОВКИ ]',
    'mission_obj': 'ОПЕРАТИВНАЯ ЗАДАЧА',
    
    # Расширенная теория (текст будет длинным)
    'sql_theory_p1': 'SQL-инъекция — это метод атаки, при котором злоумышленник внедряет вредоносный SQL-код в запрос. Это возможно, если приложение неправильно фильтрует кавычки (\') или спецсимволы.',
    'sql_theory_p2': 'Основные этапы эксплуатации:\n1. BREAK: Ввод (\') для вызова ошибки.\n2. ANALYZE: Использование ORDER BY для подсчета колонок.\n3. EXTRACT: Применение UNION SELECT для вывода данных из других таблиц.',
    'sql_theory_warning': 'ВНИМАНИЕ: Всегда закрывайте оригинальный запрос комментарием (-- или #), чтобы избежать ошибок синтаксиса.',

    # Квиз (6 вопросов)
    'quiz_title': 'ТЕСТ НА ДОПУСК К СИСТЕМЕ',
    'q1_q': 'Какой символ чаще всего используется для проверки уязвимости?',
    'q1_a1': 'Одинарная кавычка (\')',
    'q1_a2': 'Знак процента (%)',
    
    'q2_q': 'Зачем в конце пейлоада ставят -- ?',
    'q2_a1': 'Чтобы закомментировать остаток запроса',
    'q2_a2': 'Чтобы увеличить скорость ответа',
    
    'q3_q': 'Что делает оператор UNION SELECT?',
    'q3_a1': 'Объединяет результаты вашего запроса с основным',
    'q3_a2': 'Удаляет данные из текущей таблицы',

    'q4_q': 'Как определить количество колонок в таблице?',
    'q4_a1': 'Использовать ORDER BY с числами',
    'q4_a2': 'Посчитать количество букв в названии таблицы',

    'q5_q': 'Какое условие всегда истинно в SQL?',
    'q5_a1': '1=1',
    'q5_a2': 'admin=true',

    'q6_q': 'Где выполняется SQL-инъекция?',
    'q6_a1': 'На стороне сервера базы данных',
    'q6_a2': 'В браузере пользователя (на клиенте)',
    },
    'kz': {
        'dashboard': 'Басқару панелі',
        'profile': 'Хакер профилі',
        'balance': 'Теңгерім',
        'xp': 'Тәжірибе (XP)',
        'sql_title': 'SQL инъекциялары',
        'sql_desc': 'Мәліметтер базасына осал өрістер арқылы кіру.',
        'xss_title': 'XSS шабуылдары',
        'xss_desc': 'Клиент жағына зиянды скрипттерді енгізу.',
        'exit': 'Шығу',
        'sql_header': '[!] SQL_НЫСАН_ИНФРАҚҰРЫЛЫМЫ',
        'sql_path': 'ЖОЛ: root/targets/level_',
        'sql_intel': 'БАРЛАУ МӘЛІМЕТТЕРІ: ',
        'abort_btn': 'МИССИЯНЫ_ТОҚТАТУ',
        'theory_title': '> [ ТЕОРИЯ_МОДУЛІ ]',
        'outcome_title': 'КҮТІЛЕТІН_НӘТИЖЕ:',
        'mission_obj': 'МИССИЯ МАҚСАТЫ',
        'auth_gate': '> ЕНГІЗУДІ ТЕСТІЛЕУ (QUERY_TEST)',
        'sql_stats_title': 'ОСАЛДЫҚТЫ ТАЛДАУ: OWASP_TOP_10',
        'sql_stats_text': 'Инъекциялар тұрақты түрде OWASP Top 10-ға кіреді. Осалдық пайдаланушы деректері интерпретаторға команданың бөлігі ретінде берілгенде пайда болады.',
        'sql_global_info': 'SQL инъекциясы шабуылдаушыға мәліметтер базасына сұраныстарға араласуға мүмкіндік береді.',
        'db_structure_label': 'МӘЛІМЕТТЕР БАЗАСЫНЫҢ ҚҰРЫЛЫМЫ:',
        'btn_exploit': 'СҰРАНЫСТЫ ОРЫНДАУ',
        'get_hint_label': 'НҰСҚАУ АЛУ (-${hint_price})',
        'hint_buy_confirm': 'Сенімдісің бе? Нұсқау үшін баланстан ${hint_price} алынады.',
        'shop_hint_bracket': '[ НҰСҚАУ -${hint_price} ]',
        'surrender_confirm': 'Берілесің бе? Баланстан ${surrender_price} алынады.',
        'low_balance_for_hint': '⚠ ТӨМЕН БАЛАНС: нұсқау үшін қаражат жеткіліксіз (${hint_price}). Күнделікті бонус +${daily_bonus} келесі кіруде.',
        'flash_not_enough_for_hint': 'Нұсқау үшін қаражат жеткіліксіз. Күнделікті бонус күтіңіз.',
        'wallet_balance_line': 'ТЕҢГЕРІМ:',
        'hint_panel_title': '[!] НҰСҚАУ_ДЕШИФРЛАНДЫ',
        'surrender_btn': 'ЖЕҢІЛІСТІ МОЙЫНДАУ (-${surrender_price})',
        'start_mission_btn': '> OVERRIDE GATEWAY',
        'abort_mission_btn': '[ ОПЕРАЦИЯНЫ ТОҚТАТУ ]',
        'access_granted_text': 'Түйін сәтті бұзылды. Жүйе бақылауда.',
        'next_level_btn': 'КЕЛЕСІ ТҮЙІНДІ БҰЗУ',
        'return_to_hub': 'ХАБҚА ҚАЙТУ',
        'sql_win_rewards': 'Сыйлық: +50 XP | +$125 теңгерімге',
        'sql_theory_html_title': 'SQL_THEORY | CORE_DATABASE',
        'sql_theory_h1': '[ МОДУЛЬ_01: SQL_ИНЪЕКЦИЯ_ТЕОРИЯСЫ ]',
        'sql_theory_p1': '> SQL инъекциясы — пайдаланушы енгізуін сұраныс мәтініне қосу арқылы СУБД сұрауының бөлігін ауыстыру, деректер SQL жолына бөлмей қосылғанда.',
        'sql_theory_p2': '> Классика: query = "SELECT * FROM users WHERE login = \'" + login + "\'" — login ішіне тікелей SQL енгізілуі мүмкін.',
        'sql_theory_p3': '> Кіруді айналып өту: тырнақша жолды жабады, OR 1=1 шартты әрқашан рас етеді; -- немесе # түпнұсқа сұраныстың соңын кесіп тастайды.',
        'sql_theory_p4': '> UNION SELECT екі SELECT нәтижесін біріктіреді; баған саны мен түрлері сәйкес болуы керек — жиі ORDER BY n арқылы таңдалады.',
        'sql_theory_p5': '> MySQL-де information_schema (tables, columns) файлсыз БД құрылымын білуге көмектеседі.',
        'sql_theory_p6': '> Blind / time-based: жолдар көрінбесе де, SLEEP кідірістері немесе «иә/жоқ» жауабының айырмашылығы дерек сүзуге мүмкіндік береді.',
        'sql_theory_p7': '> Негізгі қорғаныс — параметрленген сұраныстар (prepared statements): плейсхолдерлер, мәндерді бөлек беру.',
        'sql_theory_p8': '> OWASP A03: Injection; валидация, БД-да ең аз привилегиялар және мониторингті біріктіріңіз.',
        'sql_theory_quiz_heading': '[ КВИЗ — 6 СҰРАҚ. БАРЛЫҚ ДҰРЫС ЖАУАПТАР КЕРЕК ]',
        'sql_theory_submit': 'БІЛІМДІ РАСТАУ',
        'sql_th_q1': '1/6. Жабылған тырнақшадан кейін WHERE-ке OR 1=1 қосқанда не болады?',
        'sql_th_q1o1': 'Кестені растаусыз жою',
        'sql_th_q1o2': 'WHERE шарты әрқашан рас болады',
        'sql_th_q1o3': 'MySQL root құпия сөзін өшіру',
        'sql_th_q2': '2/6. SQLi қаупін ең жақсы қандай тәсіл азайтады?',
        'sql_th_q2o1': 'Тек HTML maxlength',
        'sql_th_q2o2': 'Параметрленген сұраныстар және байланыстыру',
        'sql_th_q2o3': 'Құпия сөздерді ашық сақтау',
        'sql_th_q3': '3/6. Инъекцияда -- немесе # не үшін қолданылады?',
        'sql_th_q3o1': 'Түпнұсқа SQL қалғанын «пікірге» алу үшін',
        'sql_th_q3o2': 'Байланысты шифрлеу үшін',
        'sql_th_q3o3': 'SELECT жылдамдығын арттыру үшін',
        'sql_th_q4': '4/6. Екі сұраныс арасында сәтті UNION SELECT үшін не керек?',
        'sql_th_q4o1': 'Екі сұраныста бірдей БД атауы',
        'sql_th_q4o2': 'FILE құқығы',
        'sql_th_q4o3': 'Екі SELECT-тің сәйкес баған саны (және түрлері)',
        'sql_th_q5': '5/6. SQLi контекстінде information_schema не үшін қаралады?',
        'sql_th_q5o1': 'Қызметтік кестелерді жою',
        'sql_th_q5o2': 'Журналдауды өшіру',
        'sql_th_q5o3': 'Кесте мен баған атауларын (метадеректер) білу',
        'sql_th_q6': '6/6. Second-order SQLi дегеніміз…',
        'sql_th_q6o1': 'Зиянды енгізу сақталып, кейін басқа сұраныста орындалады',
        'sql_th_q6o2': 'Шабуыл тек HTTPS жоқ кезде ғана',
        'sql_th_q6o3': 'СУБД UNION-ды тыйым салады',
        'login_title': 'Жүйеге кіру',
        'register_title': 'Тіркелу',
        'username_label': 'Пайдаланушы аты',
        'email_label': 'Email',
        'password_label': 'Құпия сөз',
        'login_btn': 'Кіру',
        'register_btn': 'Тіркелу',
        'no_account': 'Аккаунтыңыз жоқ па?',
        'have_account': 'Аккаунтыңыз бар ма?',
        'theory_quiz_error': 'ACCESS_DENIED: барлық 6 дұрыс жауап керек.',
        'xss_theory_html_title': 'XSS_THEORY | SCRIPT_INJECTION',
        'xss_theory_h1': '[ МОДУЛЬ_02: XSS_ТЕОРИЯСЫ ]',
        'xss_theory_p1': '> XSS (Cross-Site Scripting) — басқа пайдаланушы көретін бетке орындалатын кодты (әдетте JavaScript) енгізу.',
        'xss_theory_p2': '> Reflected — payload сервер жауабында «шағылады»; Stored — сақталып, көпшілікке көрінеді; DOM-based — URL/деректерді клиенттік JS талдағандағы қате.',
        'xss_theory_p3': '> Экрандаусыз script, img onerror, svg onload, href ішіндегі javascript: бет контекстінде код орындалуына әкелуі мүмкін.',
        'xss_theory_p4': '> HttpOnly cookie document.cookie арқылы ұрлауды қиындатады, бірақ XSS-тің басқа салдарларын жоймайды.',
        'xss_theory_p5': '> CSP скрипттердің қайдан жүктелетінін шектейді; валидация және контекстік кодтаумен біріктіріңіз.',
        'xss_theory_p6': '> Контекст маңызды: HTML, атрибут, JS жолы және URL үшін кодтау әртүрлі.',
        'xss_theory_quiz_heading': '[ КВИЗ — 6 СҰРАҚ. БАРЛЫҚ ДҰРЫС ЖАУАПТАР ]',
        'xss_theory_submit': 'БІЛІМДІ РАСТАУ',
        'xss_theory_nav': '[ XSS ТЕОРИЯСЫ ]',
        'xss_th_q1': '1/6. Сәтті XSS-те зиянды JavaScript қайда орындалады?',
        'xss_th_q1o1': 'Тек қолданба серверінде',
        'xss_th_q1o2': 'Жертва браузерінде (клиент жағы)',
        'xss_th_q1o3': 'DNS серверінде',
        'xss_th_q2': '2/6. Content-Security-Policy (CSP) не үшін қолданылады?',
        'xss_th_q2o1': 'Браузерге скрипттерді қайдан жүктеуге/орындауға рұқсат ететінін шектеу',
        'xss_th_q2o2': 'CSS жүктелуін жылдамдату',
        'xss_th_q2o3': 'HTTPS өшіру',
        'xss_th_q3': '3/6. Reflected XSS дегеніміз payload…',
        'xss_th_q3o1': 'Тек браузер cookie-де сақталады',
        'xss_th_q3o2': 'Сервер жауабына түсіп, серверде ұзақ сақталмай көрінеді',
        'xss_th_q3o3': 'Тек cron-та орындалады',
        'xss_th_q4': '4/6. <img src=x onerror=alert(1)> JS орындата ала ма?',
        'xss_th_q4o1': 'Жоқ, img скрипт орындатпайды',
        'xss_th_q4o2': 'Иә, onerror JavaScript шақыруы мүмкін',
        'xss_th_q4o3': 'Тек сурет серверде болса ғана',
        'xss_th_q5': '5/6. Шығаруды «бір рет кодтау» барлық орынға жеткілікті ме?',
        'xss_th_q5o1': 'Иә, HTML, JS және URL үшін бір алгоритм жеткілікті',
        'xss_th_q5o2': 'Жоқ, контекстке қарай кодтау керек',
        'xss_th_q5o3': 'Жоқ, тек maxlength жеткілікті',
        'xss_th_q6': '6/6. Сессия cookie үшін HttpOnly…',
        'xss_th_q6o1': 'Кез келген XSS мүмкін емес етеді',
        'xss_th_q6o2': 'document.cookie арқылы оқуды қиындатады, бірақ барлық XSS сценарийлерін жоймайды',
        'xss_th_q6o3': 'Браузерде сессияны өшіреді',
    },
    'en': {
        'dashboard': 'Dashboard',
        'profile': 'Hacker Profile',
        'balance': 'Balance',
        'xp': 'Experience (XP)',
        'sql_title': 'SQL Injections',
        'sql_desc': 'Database penetration through vulnerable input fields.',
        'xss_title': 'XSS Attacks',
        'xss_desc': 'Injecting malicious scripts into the client side.',
        'exit': 'Logout',
        'sql_header': '[!] SQL_TARGET_INFRASTRUCTURE',
        'sql_path': 'PATH: root/targets/level_',
        'sql_intel': 'DATA_INTEL: ',
        'abort_btn': 'ABORT_MISSION',
        'theory_title': '> [ THEORY_MODULE ]',
        'outcome_title': 'EXPECTED_OUTCOME:',
        'mission_obj': 'MISSION_OBJECTIVE',
        'auth_gate': '> INPUT_TESTING (QUERY_TEST)',
        'sql_stats_title': 'VULNERABILITY_ANALYSIS: OWASP_TOP_10',
        'sql_stats_text': 'Injections are consistently in the OWASP Top 10. Vulnerability occurs when user data is sent to an interpreter as part of a command.',
        'sql_global_info': 'SQL injection allows an attacker to interfere with database queries.',
        'db_structure_label': 'DATABASE STRUCTURE:',
        'btn_exploit': 'EXECUTE QUERY',
        'get_hint_label': 'GET HINT (-${hint_price})',
        'hint_buy_confirm': 'Spend ${hint_price} from your balance for this hint? Are you sure?',
        'shop_hint_bracket': '[ HINT -${hint_price} ]',
        'surrender_confirm': 'Surrender? ${surrender_price} will be deducted from your balance.',
        'low_balance_for_hint': '⚠ LOW_BALANCE: not enough balance for a hint (${hint_price}). Daily bonus +${daily_bonus} on next login.',
        'flash_not_enough_for_hint': 'Insufficient funds for the hint. Wait for the daily bonus.',
        'wallet_balance_line': 'BALANCE:',
        'hint_panel_title': '[!] HINT_DECRYPTED',
        'surrender_btn': 'SURRENDER (-${surrender_price})',
        'start_mission_btn': '> OVERRIDE GATEWAY',
        'abort_mission_btn': '[ ABORT OPERATION ]',
        'access_granted_text': 'Node successfully breached. System under control.',
        'next_level_btn': 'BREACH NEXT NODE',
        'return_to_hub': 'RETURN TO HUB',
        'sql_win_rewards': 'Reward: +50 XP | +$125 balance',
        'sql_theory_html_title': 'SQL_THEORY | CORE_DATABASE',
        'sql_theory_h1': '[ MODULE_01: SQL_INJECTION_THEORY ]',
        'sql_theory_p1': '> SQL injection alters part of a database query via user input when values are concatenated into SQL text instead of bound safely.',
        'sql_theory_p2': '> Classic bug: query = "SELECT * FROM users WHERE login = \'" + login + "\'" — attacker-controlled SQL can be injected into login.',
        'sql_theory_p3': '> Auth bypass: a quote closes the string; OR 1=1 makes the predicate always true; -- or # comments out the rest of the original query.',
        'sql_theory_p4': '> UNION SELECT merges two result sets; column count/types must align — attackers often probe with ORDER BY n.',
        'sql_theory_p5': '> In MySQL, information_schema (tables, columns) reveals schema metadata without filesystem access.',
        'sql_theory_p6': '> Blind / time-based SQLi: no visible rows, but delays (SLEEP) or boolean differences still leak data.',
        'sql_theory_p7': '> Primary app-layer defense: parameterized queries (prepared statements) with bound parameters, not string interpolation.',
        'sql_theory_p8': '> OWASP lists this as A03:2021 Injection; combine validation, least-privilege DB accounts, and query monitoring.',
        'sql_theory_quiz_heading': '[ QUIZ — 6 QUESTIONS. ALL ANSWERS MUST BE CORRECT ]',
        'sql_theory_submit': 'CONFIRM KNOWLEDGE',
        'sql_th_q1': '1/6. What does adding OR 1=1 after a closed quote in a vulnerable WHERE clause do?',
        'sql_th_q1o1': 'Drops the table without confirmation',
        'sql_th_q1o2': 'Makes the WHERE condition always true',
        'sql_th_q1o3': 'Disables the MySQL root password',
        'sql_th_q2': '2/6. What best reduces SQLi risk in a typical web app?',
        'sql_th_q2o1': 'HTML maxlength only',
        'sql_th_q2o2': 'Parameterized queries and parameter binding',
        'sql_th_q2o3': 'Store passwords in plaintext for debugging',
        'sql_th_q3': '3/6. Why are -- or # often used at the end of a payload?',
        'sql_th_q3o1': 'To comment out the remainder of the original SQL',
        'sql_th_q3o2': 'To enable connection encryption',
        'sql_th_q3o3': 'To speed up SELECT',
        'sql_th_q4': '4/6. What is required for UNION SELECT between two queries to work?',
        'sql_th_q4o1': 'Same database name in both queries',
        'sql_th_q4o2': 'FILE privilege on the server',
        'sql_th_q4o3': 'Compatible column count (and types) in both SELECTs',
        'sql_th_q5': '5/6. Why query information_schema during SQLi?',
        'sql_th_q5o1': 'To delete system tables',
        'sql_th_q5o2': 'To disable logging',
        'sql_th_q5o3': 'To learn table/column names (metadata)',
        'sql_th_q6': '6/6. Second-order SQLi means…',
        'sql_th_q6o1': 'Malicious input is stored and executed later in another query',
        'sql_th_q6o2': 'Attack works only without HTTPS',
        'sql_th_q6o3': 'The DBMS forbids UNION',
        'login_title': 'Login',
        'register_title': 'Register',
        'username_label': 'Username',
        'email_label': 'Email',
        'password_label': 'Password',
        'login_btn': 'Login',
        'register_btn': 'Register',
        'no_account': "Don't have an account?",
        'have_account': 'Already have an account?',
        'theory_quiz_error': 'ACCESS_DENIED: all 6 answers must be correct.',
        'xss_theory_html_title': 'XSS_THEORY | SCRIPT_INJECTION',
        'xss_theory_h1': '[ MODULE_02: XSS_THEORY ]',
        'xss_theory_p1': '> XSS (Cross-Site Scripting) is injecting executable code (usually JavaScript) into a page another user will see.',
        'xss_theory_p2': '> Reflected — payload bounces in the server response; Stored — saved and shown to many users; DOM-based — flaw in client-side JS parsing URL/data.',
        'xss_theory_p3': '> Without encoding, tags and attributes (script, img onerror, svg onload, javascript: in href) can execute in page context.',
        'xss_theory_p4': '> HttpOnly cookies are harder to steal via document.cookie but do not stop other XSS impacts (DOM changes, actions as the user).',
        'xss_theory_p5': '> Content-Security-Policy limits where scripts may load; combine with validation and contextual encoding.',
        'xss_theory_p6': '> Context matters: encoding differs for HTML, attributes, JS strings, and URLs.',
        'xss_theory_quiz_heading': '[ QUIZ — 6 QUESTIONS. ALL ANSWERS MUST BE CORRECT ]',
        'xss_theory_submit': 'CONFIRM KNOWLEDGE',
        'xss_theory_nav': '[ XSS THEORY ]',
        'xss_th_q1': '1/6. Where does malicious JavaScript run in a successful XSS attack?',
        'xss_th_q1o1': 'Only on the application server',
        'xss_th_q1o2': "In the victim's browser (client-side)",
        'xss_th_q1o3': 'On a DNS server',
        'xss_th_q2': '2/6. What is Content-Security-Policy (CSP) mainly for?',
        'xss_th_q2o1': 'Restricting where the browser may load and execute scripts',
        'xss_th_q2o2': 'Speeding up CSS downloads',
        'xss_th_q2o3': 'Disabling HTTPS',
        'xss_th_q3': '3/6. Reflected XSS means the payload…',
        'xss_th_q3o1': 'Is stored only in browser cookies',
        'xss_th_q3o2': 'Appears in the server response without long-term server-side storage',
        'xss_th_q3o3': 'Runs only in a cron job',
        'xss_th_q4': '4/6. Can <img src=x onerror=alert(1)> execute JavaScript?',
        'xss_th_q4o1': 'No, img never runs scripts',
        'xss_th_q4o2': 'Yes, onerror can invoke JavaScript',
        'xss_th_q4o3': 'Only if the image file exists on the server',
        'xss_th_q5': '5/6. Is one generic encoding pass enough everywhere on the page?',
        'xss_th_q5o1': 'Yes, one algorithm covers HTML, JS, and URLs',
        'xss_th_q5o2': 'No — encode according to context (HTML, attribute, script, URL)',
        'xss_th_q5o3': 'No — maxlength alone is enough',
        'xss_th_q6': '6/6. HttpOnly on a session cookie…',
        'xss_th_q6o1': 'Makes any XSS impossible',
        'xss_th_q6o2': 'Blocks reading the cookie via document.cookie but not all XSS scenarios',
        'xss_th_q6o3': 'Disables sessions in the browser',
    }
}

# Экономика лаборатории (совпадайте DAILY_BONUS с models.check_and_give_daily_bonus)
HINT_PRICE = 150
SURRENDER_PRICE = 100
DAILY_BONUS = 100

# Ключи, в строках которых есть {hint_price}, {surrender_price}, {daily_bonus}
_I18N_FORMAT_KEYS = frozenset({
    'get_hint_label', 'hint_buy_confirm', 'surrender_btn',
    'shop_hint_bracket', 'surrender_confirm', 'low_balance_for_hint',
})


def t_for_lang(lang_code: str) -> dict:
    """Переводы для языка + подстановка числовых плейсхолдеров."""
    raw = translations.get(lang_code, translations['ru'])
    subs = {
        'hint_price': HINT_PRICE,
        'surrender_price': SURRENDER_PRICE,
        'daily_bonus': DAILY_BONUS,
    }
    out = dict(raw)
    for key in _I18N_FORMAT_KEYS:
        if key in out:
            out[key] = out[key].format(**subs)
    return out


def get_levels_data(lang):
    path = os.path.join(BASE_DIR, 'levels_sql.json')
    with open(path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
 
    lang = lang if lang in all_data else 'ru'
    result = {}
    for lid_str, data in all_data[lang].items():
        lid = int(lid_str)
        data['id'] = lid
        result[lid] = data
    return result


@app.route('/CSRF')
@login_required
def csrf_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_csrf.json', lang)
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid = lvl['id']
        lvl['completed'] = is_completed(uid, 'csrf', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'csrf', lid - 1) or is_unlocked(uid, 'csrf', lid)
    return render_template('csrf_levels.html', levels=levels.values())
 
 
@app.route('/CSRF/<int:level_id>', methods=['GET', 'POST'])
@login_required
def csrf_level(level_id):
    lang       = session.get('lang', 'ru')
    levels     = load_levels('levels_csrf.json', lang)
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('csrf_labs'))
 
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
 
 
@app.route('/PATH')
@login_required
def path_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_path_traversal.json', lang)
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid = lvl['id']
        lvl['completed'] = is_completed(uid, 'path', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'path', lid - 1) or is_unlocked(uid, 'path', lid)
    return render_template('path_levels.html', levels=levels.values())
 
 
@app.route('/PATH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def path_level(level_id):
    lang       = session.get('lang', 'ru')
    levels     = load_levels('levels_path_traversal.json', lang)
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('path_labs'))
 
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
 
# ── CSRF: вспомогательный маршрут — "сервер жертвы" ──
# Имитирует успешное изменение email/перевод (для демонстрации атаки)
@app.route('/csrf_victim_action', methods=['GET', 'POST'])
@login_required
def csrf_victim_action():
    """Имитация уязвимого endpoint без CSRF-защиты."""
    action = request.args.get('action') or request.form.get('action', '')
    return f"ACTION_EXECUTED: {action}", 200


WEAK_PASSWORDS = ['password', '123456', 'admin', 'qwerty', 'letmein',
                  'welcome', 'monkey', 'dragon', 'master', '111111']
AUTH_TARGET_PASSWORD = 'dragon'  # правильный ответ
 
# Фейковый JWT для LVL 2
def make_fake_jwt(payload: dict) -> str:
    header  = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b'=').decode()
    payload_b = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    return f"{header}.{payload_b}."
 
def decode_fake_jwt(token: str) -> dict | None:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        payload_b = parts[1] + '=='
        return json.loads(base64.urlsafe_b64decode(payload_b).decode())
    except Exception:
        return None
 
# Правильный токен для LVL 3 (md5 от фиксированного времени для демо)
AUTH_RESET_TOKEN = hashlib.md5(b'1743465600').hexdigest()  # фиксированный timestamp
 
 
@app.route('/AUTH')
@login_required
def auth_labs():
    lang   = session.get('lang', 'ru')
    levels = load_levels('levels_auth.json', lang)
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid = lvl['id']
        lvl['completed'] = is_completed(uid, 'auth', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'auth', lid - 1) or is_unlocked(uid, 'auth', lid)
    return render_template('auth_levels.html', levels=levels.values())
 
 
@app.route('/AUTH/<int:level_id>', methods=['GET', 'POST'])
@login_required
def auth_level(level_id):
    lang       = session.get('lang', 'ru')
    levels     = load_levels('levels_auth.json', lang)
    level_data = levels.get(level_id)
    if not level_data:
        return redirect(url_for('auth_labs'))
 
    user    = current_user()
    uid     = user['id']
    unlocked = level_id == 1 or is_completed(uid, 'auth', level_id - 1) or is_unlocked(uid, 'auth', level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='auth')
 
    already     = is_completed(uid, 'auth', level_id)
    hint_bought = has_hint(uid, 'auth', level_id)
    message     = ""
    is_won      = False
    extra        = {}  # доп. данные для шаблона
 
    if request.method == 'POST':
 
        # ── LVL 1: брутфорс — угадай пароль ──
        if level_id == 1:
            password = request.form.get('password', '').strip()
            if password == AUTH_TARGET_PASSWORD:
                is_won = True
            else:
                message = f"❌ Неверный пароль: '{password}'. Попробуй другой из списка."
 
        # ── LVL 2: подделка JWT alg:none ──
        elif level_id == 2:
            token = request.form.get('jwt_token', '').strip()
            payload = decode_fake_jwt(token)
            if payload and payload.get('role') == 'admin':
                is_won = True
            else:
                # Выдаём юзеру токен с ролью user чтобы он понял структуру
                demo_token = make_fake_jwt({"username": "hacker", "role": "user"})
                extra['demo_token'] = demo_token
                message = f"❌ Недостаточно прав. Роль: {payload.get('role', 'неизвестно') if payload else 'невалидный токен'}"
 
        # ── LVL 3: предсказуемый токен ──
        elif level_id == 3:
            reset_token = request.form.get('reset_token', '').strip()
            if reset_token == AUTH_RESET_TOKEN:
                is_won = True
            else:
                # Подсказка — показываем timestamp
                import time
                extra['hint_ts'] = 1743465600
                extra['hint_md5_preview'] = AUTH_RESET_TOKEN[:8] + '...'
                message = "❌ Неверный токен. Подсказка: токен = md5(1743465600)"
 
        log_attempt(uid, 'auth', level_id, is_won,
                    request.form.get('password') or request.form.get('jwt_token') or request.form.get('reset_token') or '')
 
        if is_won and not already:
            mark_completed(uid, 'auth', level_id)
            add_reward(uid, xp=150, balance=250)
            message = "✅ AUTH BYPASS SUCCESS!"
 
    # Для LVL 2 всегда показываем demo токен
    if level_id == 2 and 'demo_token' not in extra:
        extra['demo_token'] = make_fake_jwt({"username": "hacker", "role": "user"})
 
    return render_template(
        'auth.html',
        level=level_id,
        level_data=level_data,
        message=message,
        hint_bought=hint_bought,
        is_already_completed=already or is_won,
        is_won=is_won,
        weak_passwords=WEAK_PASSWORDS,
        extra=extra,
    )
 
@app.route('/profile')
@login_required
def profile():
    user = current_user()
    uid = user['id']
    
    # Получаем звание и прогресс до следующего ранга
    rank_info = get_rank(user['xp'])
    
    # Получаем статистику (пройдено уровней, всего попыток)
    stats = get_user_stats(uid)
    
    return render_template(
        'profile.html',
        user=user,
        rank=rank_info,
        stats=stats
    )
def rank_progress(xp):

    ranks = [
        ("Newbie",0),
        ("Script Kiddie",100),
        ("White Hat",300),
        ("Elite",700)
    ]

    for i in range(len(ranks)-1):
        name,start = ranks[i]
        next_name,next_start = ranks[i+1]

        if xp < next_start:
            progress = (xp-start)/(next_start-start)*100
            return name, progress, next_name

    return "Elite",100,None
# ──────────────────────────────────────────────
# Context processor — данные текущего юзера в шаблонах
# ──────────────────────────────────────────────
@app.context_processor
def inject_globals():
    lang = session.get('lang', 'ru')
    user = current_user()
    rank = get_rank(user['xp']) if user else None
    return {
        't': t_for_lang(lang),
        'curr_lang': lang,
        'current_user': user,
        'rank': rank,
        'hint_price': HINT_PRICE,
        'surrender_price': SURRENDER_PRICE,
        'daily_bonus': DAILY_BONUS,
    }


# ──────────────────────────────────────────────
# МАРШРУТЫ: Авторизация
# ──────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('index'))

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
                return redirect(url_for('login'))
            else:
                flash(result.get("error", "Ошибка регистрации"), "error")

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = get_user_by_username(username)

        if user and check_password(password, user['password']):
            session.clear()
            session['user_id'] = user['id']
            session['lang']    = session.get('lang', 'ru')
            update_last_login(user['id'])
            check_and_give_daily_bonus(user['id'])
            return redirect(url_for('index'))
        else:
            flash("Неверный логин или пароль", "error")

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ──────────────────────────────────────────────
# МАРШРУТЫ: Основные страницы
# ──────────────────────────────────────────────

@app.route('/')
@app.route('/dashboard')
@login_required
def index():
    user = current_user()
    uid  = user['id']
 
    # Дневной бонус (уже есть при логине, но дублируем для надёжности)
    check_and_give_daily_bonus(uid)
 
    # Защита от отрицательного баланса — если баланс < 0, поднимаем до 50
    if user['balance'] < 0:
        from models import get_db
        conn = get_db()
        conn.execute("UPDATE users SET balance = 50 WHERE id = ? AND balance < 0", (uid,))
        conn.commit()
        conn.close()
 
    sql_done = sum(1 for i in range(1, 7) if is_completed(uid, 'sql', i))
    xss_done = sum(1 for i in range(1, 6) if is_completed(uid, 'xss', i))
 
    return render_template('index.html', sql_done=sql_done, xss_done=xss_done)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in translations:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))



@app.route('/leaderboard')
@login_required
def leaderboard():
    board = get_leaderboard(10)
    user  = current_user()
    for i, row in enumerate(board):
        row['rank_info'] = get_rank(row['xp'])
        row['is_me']     = (row['username'] == user['username'])
    return render_template('leaderboard.html', board=board)


# ──────────────────────────────────────────────
# МАРШРУТЫ: SQL Injection
# ──────────────────────────────────────────────
@app.route('/sql-injection/theory')
def sql_theory():
    return render_template('sql_theory.html')


@app.route('/XSS/theory')
def xss_theory():
    return render_template('xss_theory.html')


def _theory_quiz_solved() -> bool:
    """Все 6 вопросов: у каждого выбран вариант value=\"corr\"."""
    for i in range(1, 7):
        if request.form.get(f'q{i}') != 'corr':
            return False
    return True


@app.route('/verify-theory/<category>', methods=['POST'])
@login_required
def verify_theory(category):
    if category not in ('sql', 'xss'):
        return redirect(url_for('index'))
    lang = session.get('lang', 'ru')
    terr = t_for_lang(lang)
    err_msg = terr.get('theory_quiz_error', 'ACCESS_DENIED')
    if _theory_quiz_solved():
        session[f'{category}_theory_passed'] = True
        if category == 'sql':
            return redirect(url_for('sql_labs'))
        return redirect(url_for('xss_labs'))
    if category == 'sql':
        return render_template('sql_theory.html', error=err_msg)
    return render_template('xss_theory.html', error=err_msg)
    
@app.route('/sql-injection')
@login_required
def sql_labs():
    lang = session.get('lang', 'ru')
    levels = get_levels_data(lang)
    user = current_user()
    
    if not user:
        return redirect(url_for('login'))

    uid = user['id']

    # Добавляем информацию о статусе для каждого уровня
    for lvl in levels.values():
        lid = lvl['id']
        lvl['completed'] = is_completed(uid, 'sql', lid)
        lvl['unlocked']  = is_unlocked(uid, 'sql', lid) or (lid == 1)  # 1 уровень всегда открыт
        
        # Дополнительно можно добавить прогресс (сколько попыток и т.д.)
        # lvl['attempts'] = get_attempt_count(uid, 'sql', lid)  # если позже добавишь

    return render_template('sql_levels.html', levels=levels.values())


@app.route('/sql-injection/<int:level_id>', methods=['GET', 'POST'])
@login_required
def sql_level(level_id):
    curr_lang = session.get('lang', 'ru')
    levels = get_levels_data(curr_lang)
    level_data = levels.get(level_id)

    if not session.get('sql_theory_passed'):
        return redirect(url_for('sql_theory'))

    if not level_data:
        return redirect(url_for('sql_labs'))

    user = current_user()
    uid = user['id']

    if not is_unlocked(uid, 'sql', level_id):
        return render_template('access_denied.html', level_id=level_id)

    is_won = False
    is_already_completed = is_completed(uid, 'sql', level_id)
    hint_bought = has_hint(uid, 'sql', level_id)
    message = None
    rows = None

    if request.method == 'POST':
        conn, table = get_db_for_level(level_id)
        c = conn.cursor()
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        print(f"[LEVEL {level_id}] USER INPUT: '{username}'")   # для отладки

        try:
            success = False

            # ==================== УРОВЕНЬ 1 ====================
            if level_id == 1:
                query = f"SELECT * FROM {table} WHERE username='{username}' AND password='{password}'"
                c.execute(query)
                if c.fetchone():
                    success = True

            # ==================== УРОВЕНЬ 2 ====================
            elif level_id == 2:
                # Очень мягкая фильтрация — почти ничего не убираем
                fu = username.replace(" --", "--").replace("-- ", "--")
                fp = password.replace(" --", "--").replace("-- ", "--")
                
                query = f"SELECT * FROM {table} WHERE username='{fu}' AND password='{fp}'"
                c.execute(query)
                result = c.fetchone()

                if result:
                    success = True
                else:
                    # Если ничего не нашлось — явно говорим об ошибке
                    message = "ACCESS DENIED - Попробуй admin'-- или admin' #"

            # ==================== УРОВЕНЬ 3 ====================
            elif level_id == 3:
                query = f"SELECT * FROM {table} WHERE username='{username}' AND password='{password}'"
                c.execute(query)
                if c.fetchone() or "order by" in username.lower():
                    success = True

            # ==================== УРОВЕНЬ 4 ====================
            elif level_id == 4:
                # Только UNION
                if "union" in username.lower():
                    success = True
                    rows = [("1", "8.0.35 - MySQL", "FLAG{SQL_LVL_4_DONE}")]
                else:
                    message = "ACCESS DENIED - Используй UNION SELECT"

            # ==================== УРОВЕНЬ 5 ====================
            elif level_id == 5:
                # Только information_schema
                if "information_schema" in username.lower() or "table_name" in username.lower():
                    success = True
                    rows = [("secret_flags", "flag_column")]
                else:
                    message = "ACCESS DENIED - Ищи в information_schema.tables"

            # ==================== УРОВЕНЬ 6 ====================
            elif level_id == 6:
                # Только флаг
                if "flag" in username.lower() or "secret_table" in username.lower() or "secret_flags" in username.lower():
                    success = True
                    rows = [("FLAG{SQL_LVL_6_DONE}", "Congratulations!")]
                else:
                    message = "ACCESS DENIED - Ищи FLAG или secret_table"

            # Сохраняем прогресс
            if success:
                is_won = True
                if not is_already_completed:
                    mark_completed(uid, 'sql', level_id)
                    add_reward(uid, xp=50, balance=125)
                    is_already_completed = True
                    log_attempt(uid, 'sql', level_id, True, username)
            else:
                log_attempt(uid, 'sql', level_id, False, username)
                message = "ACCESS DENIED - Неправильные данные"

        except Exception as e:
            message = f"Database error: {str(e)}"
            print(f"[ERROR Level {level_id}] {e}")
        finally:
            conn.close()

    return render_template(
        'sql_injection.html',
        level=level_data,
        is_won=is_won,
        is_already_completed=is_already_completed,
        hint_bought=hint_bought,
        rows=rows,
        message=message
    )

@app.route('/start_mission/<int:level_id>')
@login_required
def start_mission(level_id):
    session[f'conf_{level_id}'] = True
    return redirect(url_for('sql_level', level_id=level_id))


@app.route('/surrender/<category>/<int:level_id>')
@login_required
def surrender(category, level_id):
    user = current_user()
    uid  = user['id']
    if category not in ('sql', 'xss', 'csrf', 'path', 'auth'):
        return redirect(url_for('index'))
    deduct_balance(uid, 150)
    from models import get_db
    conn = get_db()
    conn.execute("UPDATE users SET balance = MAX(balance, 0) WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    labs = {
        'sql': 'sql_labs', 'xss': 'xss_labs',
        'csrf': 'csrf_labs', 'path': 'path_labs', 'auth': 'auth_labs'
    }
    return redirect(url_for(labs[category]))
 
    

@app.route('/buy_xss_level/<int:level_id>')
@login_required
def buy_xss_level(level_id):
    user  = current_user()
    price = 100
    if deduct_balance(user['id'], price):
        mark_unlocked(user['id'], 'xss', level_id)
        return redirect(url_for('xss_level', level_id=level_id))
    flash("Недостаточно средств!", "warning")
    return redirect(url_for('xss_labs'))

@app.route('/buy_level/<int:level_id>')
@login_required
def buy_level(level_id):
    user  = current_user()
    price = 100
    if deduct_balance(user['id'], price):
        mark_unlocked(user['id'], 'sql', level_id)
        return redirect(url_for('sql_level', level_id=level_id))
    return redirect(url_for('sql_labs', message="NOT_ENOUGH_CASH"))


@app.route('/buy_hint/<category>/<int:level_id>')
@login_required
def buy_hint(category, level_id):
    """Универсальная покупка подсказки для sql и xss."""
    user = current_user()
    uid  = user['id']
 
    # Проверяем категорию
    if category not in ('sql', 'xss'):
        return redirect(url_for('index'))
 
    # Уже куплена — просто редирект обратно
    if has_hint(uid, category, level_id):
        if category == 'sql':
            return redirect(url_for('sql_level', level_id=level_id))
        return redirect(url_for('xss_level', level_id=level_id))
 
    # Покупаем
    if deduct_balance(uid, HINT_PRICE):
        mark_hint_bought(uid, category, level_id)
    else:
        flash(t_for_lang(session.get('lang', 'ru'))['flash_not_enough_for_hint'], "warning")
 
    if category == 'sql':
        return redirect(url_for('sql_level', level_id=level_id))
    return redirect(url_for('xss_level', level_id=level_id))


# ──────────────────────────────────────────────
# МАРШРУТЫ: XSS
# ──────────────────────────────────────────────

# 1. Это ПРОСТО функция-помощник. Никаких @app.route здесь!
def get_xss_levels_data(lang):
    import json
    path = os.path.join(BASE_DIR, 'levels_xss.json')
    with open(path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    lang = lang if lang in all_data else 'ru'
    result = {}
    for lid_str, data in all_data[lang].items():
        lid = int(lid_str)
        data['id'] = lid
        result[lid] = data
    return result

# 2. А вот это — СТРАНИЦА. Вешаем декораторы сюда.
@app.route('/XSS')
@login_required
def xss_labs():
    if not session.get('xss_theory_passed'):
        return redirect(url_for('xss_theory'))
    lang   = session.get('lang', 'ru')
    levels = get_xss_levels_data(lang)
    user   = current_user()
    uid    = user['id']
    for lvl in levels.values():
        lid = lvl['id']
        lvl['completed'] = is_completed(uid, 'xss', lid)
        lvl['unlocked']  = lid == 1 or is_completed(uid, 'xss', lid - 1) or is_unlocked(uid, 'xss', lid)
    return render_template('xss_levels.html', levels=levels.values())


@app.route('/XSS/<int:level_id>', methods=['GET', 'POST'])
@login_required
def xss_level(level_id):
    if not session.get('xss_theory_passed'):
        return redirect(url_for('xss_theory'))
    lang       = session.get('lang', 'ru')
    levels     = get_xss_levels_data(lang)
    level_data = levels.get(level_id)
 
    if not level_data:
        return redirect(url_for('xss_labs'))
 
    user    = current_user()
    uid     = user['id']
 
    # Проверка доступа (как в SQL)
    unlocked = level_id == 1 or is_completed(uid, 'xss', level_id - 1) or is_unlocked(uid, 'xss', level_id)
    if not unlocked:
        return render_template('access_denied.html', level_id=level_id, category='xss')
 
    already     = is_completed(uid, 'xss', level_id)
    hint_bought = has_hint(uid, 'xss', level_id)
    message     = ""
    is_won      = False
 
    if request.method == 'POST' and not already:
        val       = request.form.get('user_input', '')
        val_lower = val.lower().strip()
 
        import re
 
        # ── LVL 1: простой <script>alert ──
        if level_id == 1:
            if '<script>' in val_lower and 'alert' in val_lower:
                is_won = True
 
        # ── LVL 2: фильтр нижнего регистра ──
        elif level_id == 2:
            blocked    = bool(re.search(r'<script>', val_lower))
            has_script = bool(re.search(r'<\s*s\s*c\s*r\s*i\s*p\s*t\s*>', val, re.IGNORECASE))
            if has_script and not blocked and 'alert' in val_lower:
                is_won = True
 
        # ── LVL 3: обработчики событий (без script) ──
        elif level_id == 3:
            has_script_tag = bool(re.search(r'<\s*script', val_lower))
            has_event      = bool(re.search(r'on(error|load|mouseover|click|focus)\s*=', val_lower))
            if has_event and not has_script_tag and 'alert' in val_lower:
                is_won = True
 
        # ── LVL 4: закодированный payload (alert заблокирован) ──
        elif level_id == 4:
            direct_alert = bool(re.search(r'\balert\b', val_lower))
            has_encoded  = any(x in val_lower for x in [
                '\\u00', 'string.fromcharcode', 'eval(', 'atob(',
                'confirm(', 'prompt('
            ])
            if has_encoded and not direct_alert:
                is_won = True
 
        # ── LVL 5: javascript: URI или data: URI ──
        elif level_id == 5:
            has_js_proto = bool(re.search(r'javascript\s*:', val_lower))
            has_data_uri = bool(re.search(r'data\s*:\s*text/html', val_lower))
            if (has_js_proto or has_data_uri) and 'alert' in val_lower:
                is_won = True
 
        log_attempt(uid, 'xss', level_id, is_won, val[:300])
 
        if is_won and not already:
            mark_completed(uid, 'xss', level_id)
            add_reward(uid, xp=100, balance=125)
            message = "✅ XSS SUCCESS!"
        elif not is_won:
            message = "❌ Payload не сработал. Попробуй ещё раз."
 
    return render_template(
        "xss.html",
        level=level_id,
        level_data=level_data,
        description=level_data['desc'],
        level_hint=level_data['hint'],
        message=message,
        hint_bought=hint_bought,
        is_already_completed=already or is_won,
        is_won=is_won,
    )

# ──────────────────────────────────────────────
# МАРШРУТЫ: Достижения
# ──────────────────────────────────────────────

@app.route('/achievements')
@login_required
def achievements():
    user = current_user()
    uid  = user['id']
    progress = {
        'sql_master': is_completed(uid, 'sql', 1) and is_completed(uid, 'sql', 2),
        'xss_pro':    is_completed(uid, 'xss', 1),
        'rich_kid':   user['balance'] >= 1000,
        'sql_legend': all(is_completed(uid, 'sql', i) for i in range(1, 7)),
    }
    return render_template('achievements.html', progress=progress)


# ──────────────────────────────────────────────
# МАРШРУТЫ: Админ-панель
# ──────────────────────────────────────────────

@app.route('/internal/system/console/v2')
@login_required
def admin_panel():
    from models import get_db, add_reward # Импортируем внутри, если нужно
    
    # 1. Сначала определяем переменную user!
    user = current_user() 
    
    # 2. Проверяем, существует ли он и админ ли он
    if not user or not user['is_admin']:
        return "404 Not Found", 404
    
    # Словарь для админки
    texts = {
        'kz': {
            'title': 'ЖҮЙЕНІ_БАСҚАРУ_ПАНЕЛІ',
            'users_list': 'АНЫҚТАЛҒАН_ПАЙДАЛАНУШЫЛАР',
            'stats': 'ДЕҢГЕЙЛЕРДІҢ_СТАТИСТИКАСЫ',
            'feed': 'ЖАНДЫ_ШАБУЫЛ_ТАСПАСЫ',
            'back': '_ БАСҚЫ_БЕТКЕ_ҚАЙТУ',
            'title': 'ЖҮЙЕНІ_БАСҚАРУ_ПАНЕЛІ',
            'btn_money': 'АҚША_БЕРУ', # Вместо Give Money
            'btn_ban': 'БҰҒАТТАУ',
        },
        'ru': {
            'title': 'ПАНЕЛЬ_УПРАВЛЕНИЯ_СИСТЕМОЙ',
            'users_list': 'ИДЕНТИФИЦИРОВАННЫЕ_ПОЛЬЗОВАТЕЛИ',
            'stats': 'АНАЛИЗ_АКТИВНОСТИ_УРОВНЕЙ',
            'feed': 'ЖИВОЙ_ЛОГ_АТАК',
            'back': '_ ВЕРНУТЬСЯ_В_ГЛАВНОЕ_МЕНЮ'
        },
        'en': {
            'title': 'SYSTEM_CONTROL_PANEL',
            'users_list': 'IDENTIFIED_USERS',
            'stats': 'LEVEL_ACTIVITY_ANALYSIS',
            'feed': 'LIVE_ATTACK_FEED',
            'back': '_ RETURN_TO_CORE_DASHBOARD'
        }
    }
    
    # Определяем текущий язык (берем из сессии или конфига)
    # Предположим, у тебя язык хранится в session['lang']
    lang = session.get('lang', 'ru') 
    t = texts.get(lang, texts['en']) # Если языка нет, берем английский
    
    # 3. ТОЛЬКО ТЕПЕРЬ можно использовать user['id']
    # Я убрал авто-начисление денег при каждом входе, 
    # иначе ты будешь богатеть просто обновляя страницу админки :)
    # Но если очень хочется, оставь:
    # add_reward(user['id'], balance=100)
    
    conn = get_db()
    
    # Получаем список юзеров
    users = conn.execute(
        "SELECT id, username, email, xp, balance, created_at, last_login, is_admin FROM users ORDER BY xp DESC"
    ).fetchall()
    
    # Статистика уровней
    stats = conn.execute(
        """SELECT category, level_id,
                  COUNT(*) as total_attempts,
                  SUM(success) as successes,
                  ROUND(100.0 * SUM(success) / COUNT(*), 1) as success_rate
           FROM attempts
           GROUP BY category, level_id
           ORDER BY category, level_id"""
    ).fetchall()

    # Свежий лог атак для "жирности" админки
    recent_attempts = conn.execute("""
        SELECT a.*, u.username 
        FROM attempts a 
        JOIN users u ON a.user_id = u.id 
        ORDER BY a.created_at DESC 
        LIMIT 15
    """).fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                           users=users, 
                           stats=stats, 
                           recent_attempts=recent_attempts,
                           t=t,
                           curr_lang=lang)
@app.route('/admin/ban/<int:user_id>', methods=['POST'])
@login_required
def admin_ban_user(user_id):
    user = current_user()
    if not user or not user['is_admin']:
        return "404 Not Found", 404
        
    # Мы не даем админу забанить самого себя
    if user['id'] == user_id:
        return "You cannot ban yourself", 400

    from models import get_db
    conn = get_db()
    # Просто удаляем или можно добавить колонку is_banned. 
    # Пока давай просто удалим для простоты:
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return redirect('/internal/system/console/v2') # Возвращаемся в админку

@app.route('/admin/give_money/<int:user_id>', methods=['POST'])
@login_required
def admin_give_money(user_id):
    user = current_user()
    # Проверка на админа
    if not user or not user['is_admin']:
        return "404 Not Found", 404

    from models import add_reward
    # Начисляем, например, 100 баксов и 0 XP
    add_reward(user_id, xp=0, balance=100)
    
    # Возвращаемся обратно в админку
    return redirect('/internal/system/console/v2')
# ──────────────────────────────────────────────
# Сброс (только для разработки)
# ──────────────────────────────────────────────

@app.route('/reset')
def reset():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)