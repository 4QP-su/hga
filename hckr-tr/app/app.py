import os
from flask import Flask

from app.models import init_db
from app.config import BASE_DIR

def create_app():
    # ── Создаём приложение ──────────────────────────────────────────
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, '../templates'),
        static_folder=os.path.join(BASE_DIR, '../static'),
    )
    app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

    # ── Инициализация БД ────────────────────────────────────────────
    with app.app_context():
        init_db()

    # ── Регистрация blueprints ──────────────────────────────────────
    from app.routes.auth    import auth_bp
    from app.routes.main    import main_bp
    from app.routes.sql     import sql_bp
    from app.routes.xss     import xss_bp   
    from app.routes.csrf    import csrf_bp
    from app.routes.path_traversal import path_bp
    from app.routes.auth_bypass import authbypass_bp
    from app.routes.modules import modules_bp
    from app.routes.admin   import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(sql_bp)
    app.register_blueprint(xss_bp)
    app.register_blueprint(csrf_bp)
    app.register_blueprint(path_bp)
    app.register_blueprint(authbypass_bp)
    app.register_blueprint(modules_bp)
    app.register_blueprint(admin_bp)

    # ── Context processor — current_user и переводы в шаблонах ─────
    from flask import session
    from app.models import get_user_by_id, get_rank
    from app.config import t_for_lang, HINT_PRICE, SURRENDER_PRICE, DAILY_BONUS

    @app.context_processor
    def inject_globals():
        lang = session.get('lang', 'ru')
        uid  = session.get('user_id')
        user = get_user_by_id(uid) if uid else None
        rank = get_rank(user['xp']) if user else None
        return {
            'current_user': user,
            'current_rank': rank,
            't': t_for_lang(lang),
            'HINT_PRICE': HINT_PRICE,
            'SURRENDER_PRICE': SURRENDER_PRICE,
            'DAILY_BONUS': DAILY_BONUS,
        }

    return app

# ── Для совместимости с существующим кодом ───────────────────────
app = create_app()

if __name__ == '__main__':
    try:
        app.run(debug=True, port=5001)
    except Exception as e:
        print(f"Error starting app: {e}")
        import sys
        sys.exit(1)