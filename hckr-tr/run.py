#!/usr/bin/env python3
"""
run.py — точка входа для запуска приложения.
Запуск: python run.py
"""

from app.app import create_app

if __name__ == '__main__':
    app = create_app()
    try:
        app.run(debug=True, port=5001)
    except Exception as e:
        print(f"Error starting app: {e}")
        import sys
        sys.exit(1)