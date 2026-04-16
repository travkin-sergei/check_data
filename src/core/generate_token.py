# src/core/generate_token.py
"""
Локальный генератор безопасных API-токенов.
Не требует запуска сервера. Соответствует Python 3.12 + архитектура проекта.
"""
import os
import sys
import secrets
import string
import argparse

# Добавляем корень проекта в sys.path (опционально, если позже добавим валидацию через type_unifier)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def generate_token(length: int = 256) -> str:
    if not 200 <= length <= 300:
        raise ValueError("Длина токена должна быть строго от 200 до 300 символов")

    # Только буквы и цифры: безопасно для HTTP-заголовков, .env и логов
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Генератор API-токенов (200-300 символов)")
    parser.add_argument("-l", "--length", type=int, default=256, help="Длина токена (200-300)")
    args = parser.parse_args()

    try:
        token = generate_token(args.length)
        print(f"\n✅ Сгенерирован токен ({len(token)} символов):")
        print(token)
    except Exception as e:
        print(f"❌ Ошибка: {e}", file=sys.stderr)
        sys.exit(1)