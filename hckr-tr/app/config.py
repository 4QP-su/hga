"""
config.py — настройки приложения, экономика, загрузка переводов.
Переводы UI хранятся в translations/ui_ru.json и т.д.
Контент уровней — в levels_sql.json, levels_xss.json и т.д.
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Экономика ───────────────────────────────────────────────────
HINT_PRICE      = 150
SURRENDER_PRICE = 100
DAILY_BONUS     = 100

# Ключи строк, в которых нужна подстановка чисел
_FORMAT_KEYS = frozenset({
    'get_hint_label', 'hint_buy_confirm', 'surrender_btn',
    'shop_hint_bracket', 'surrender_confirm', 'low_balance_for_hint',
})

# ── Кэш переводов (загружаем один раз) ─────────────────────────
_UI_CACHE: dict[str, dict] = {}

def _load_ui(lang: str) -> dict:
    """Загружает переводы UI из JSON файла."""
    if lang not in _UI_CACHE:
        path = os.path.join(BASE_DIR, 'translations', f'ui_{lang}.json')
        fallback = os.path.join(BASE_DIR, 'translations', 'ui_ru.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                _UI_CACHE[lang] = json.load(f)
        except FileNotFoundError:
            with open(fallback, 'r', encoding='utf-8') as f:
                _UI_CACHE[lang] = json.load(f)
    return _UI_CACHE[lang]


def t_for_lang(lang: str) -> dict:
    """Переводы + подстановка числовых плейсхолдеров."""
    raw  = _load_ui(lang)
    subs = {
        'hint_price':      HINT_PRICE,
        'surrender_price': SURRENDER_PRICE,
        'daily_bonus':     DAILY_BONUS,
    }
    out = dict(raw)
    for key in _FORMAT_KEYS:
        if key in out:
            try:
                out[key] = out[key].format(**subs)
            except (KeyError, ValueError):
                pass
    return out


def load_levels(filename: str, lang: str) -> dict:
    """
    Загружает уровни из JSON файла.
    Возвращает dict {1: {..., 'id': 1}, 2: {...}, ...}
    """
    path = os.path.join(BASE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        all_data = json.load(f)
    lang = lang if lang in all_data else 'ru'
    result = {}
    for lid_str, data in all_data[lang].items():
        lid        = int(lid_str)
        data['id'] = lid
        result[lid] = data
    return result


SUPPORTED_LANGS = ('ru', 'kz', 'en')
