#!/usr/bin/env python3
"""
Скрипт для регистрации приложения app_file_manager и получения JWT-токена.

Этапы:
1. Регистрация приложения через API (требуется токен администратора)
2. Получение app_secret (сохранить!)
3. Аутентификация приложения и получение JWT access_token
4. Проверка доступа к файловому менеджеру

Использование:
    python register_and_get_token.py --admin-token <ADMIN_JWT_TOKEN>
    
Или для локальной регистрации напрямую через БД (без админ-токена):
    python register_and_get_token.py --direct
"""

import asyncio
import argparse
import httpx
import sys
from datetime import datetime, timezone

# Конфигурация
AUTH_SERVICE_URL = "http://localhost:8000"  # URL сервиса app_auth
FILE_MANAGER_URL = "http://localhost:8001"  # URL сервиса app_file_manager (если есть)
APP_NAME = "app_file_manager"
APP_DESCRIPTION = "Сервис управления файлами"


async def register_app_direct(app_name: str, app_description: str):
    """
    Прямая регистрация приложения через БД (обход API).
    Используется, если нет доступа к админскому токену.
    """
    print("=" * 60)
    print("РЕЖИМ ПРЯМОЙ РЕГИСТРАЦИИ ЧЕРЕЗ БД")
    print("=" * 60)
    
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from src.app_auth.models import AppCredential, User
    from src.app_auth.utils import generate_app_token, hash_app_token
    from src.app_database.config import DBConfig
    
    # Получаем строку подключения для local_auth
    try:
        db_url = DBConfig.to_asyncpg_url("local_auth")
    except Exception as e:
        print(f"\n❌ Ошибка получения DSN: {e}")
        print("   Убедитесь, что переменная DB_LOCAL_AUTH задана в .env")
        return None
    
    # Создаём движок и сессию
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Проверяем, существует ли уже приложение
        from sqlalchemy import select
        stmt = select(AppCredential).where(AppCredential.app_name == app_name)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"\n⚠️  Приложение '{app_name}' уже зарегистрировано!")
            print(f"   ID: {existing.id}")
            print(f"   Активно: {existing.is_active}")
            print(f"   Создано: {existing.created_at}")
            print("\n❗ Токен нельзя получить повторно — он показывается только один раз.")
            print("   Если токен утерян, используйте endpoint /service/apps/{app_name}/rotate-token/")
            return None
        
        # Находим админа для created_by
        stmt_user = select(User).where(User.role_id.in_([3, 4])).limit(1)
        result_user = await session.execute(stmt_user)
        admin = result_user.scalar_one_or_none()
        
        if not admin:
            print("\n❌ Не найден пользователь с ролью администратора (role_id=3 или 4)")
            print("   Создайте админа вручную или используйте API регистрацию с токеном")
            return None
        
        # Генерируем токен
        raw_token = generate_app_token(length=256)
        token_hash = await hash_app_token(raw_token)
        
        # Создаём запись
        new_cred = AppCredential(
            app_name=app_name,
            app_description=app_description,
            token_hash=token_hash,
            is_active=True,
            created_by=admin.id,
            expires_at=None  # Бессрочные учётные данные (но JWT-токены всё равно на 1 час)
        )
        
        session.add(new_cred)
        await session.commit()
        await session.refresh(new_cred)
        
        print("\n✅ Приложение успешно зарегистрировано!")
        print("\n" + "=" * 60)
        print("СОХРАНИТЕ ЭТИ ДАННЫЕ (показываются ОДИН РАЗ!):")
        print("=" * 60)
        print(f"App Name (X-App-Name):     {app_name}")
        print(f"App Secret (X-App-Secret): {raw_token}")
        print("=" * 60)
        print("\n📝 Следующий шаг: получите JWT-токен через /service/app/login/")
        print(f"   curl -X POST {AUTH_SERVICE_URL}/api/v1/auth/service/app/login/ \\")
        print(f"     -H 'X-App-Name: {app_name}' \\")
        print(f"     -H 'X-App-Secret: {raw_token}'")
        
        return {
            "app_name": app_name,
            "app_secret": raw_token
        }


async def register_app_via_api(admin_token: str, app_name: str, app_description: str):
    """Регистрация приложения через API с использованием админского токена."""
    print("=" * 60)
    print("РЕЖИМ РЕГИСТРАЦИИ ЧЕРЕЗ API")
    print("=" * 60)
    
    url = f"{AUTH_SERVICE_URL}/api/v1/auth/service/register-app/"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    data = {
        "app_name": app_name,
        "app_description": app_description
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, headers=headers)
            
            if response.status_code == 409:
                print(f"\n⚠️  Приложение '{app_name}' уже зарегистрировано")
                print("   Используйте существующий secret или обновите токен через rotate-token")
                return None
            
            response.raise_for_status()
            result = response.json()
            
            print("\n✅ Приложение успешно зарегистрировано!")
            print("\n" + "=" * 60)
            print("СОХРАНИТЕ ЭТИ ДАННЫЕ (показываются ОДИН РАЗ!):")
            print("=" * 60)
            print(f"App Name (X-App-Name):     {result['app_name']}")
            print(f"App Secret (X-App-Secret): {result['app_token']}")
            print(f"Created by:                {result['created_by']}")
            print("=" * 60)
            
            return {
                "app_name": result["app_name"],
                "app_secret": result["app_token"]
            }
            
        except httpx.HTTPStatusError as e:
            print(f"\n❌ Ошибка API: {e.response.status_code}")
            print(f"   Ответ: {e.response.text}")
            return None
        except Exception as e:
            print(f"\n❌ Ошибка подключения: {e}")
            return None


async def get_jwt_token(app_name: str, app_secret: str):
    """Получение JWT access_token через аутентификацию приложения."""
    print("\n" + "=" * 60)
    print("ПОЛУЧЕНИЕ JWT ТОКЕНА")
    print("=" * 60)
    
    url = f"{AUTH_SERVICE_URL}/api/v1/auth/service/app/login/"
    headers = {
        "X-App-Name": app_name,
        "X-App-Secret": app_secret
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers)
            
            if response.status_code != 200:
                print(f"\n❌ Ошибка аутентификации: {response.status_code}")
                print(f"   Ответ: {response.text}")
                return None
            
            tokens = response.json()
            
            print("\n✅ JWT токены получены!")
            print("\n" + "=" * 60)
            print("ACCESS TOKEN (действует 1 час):")
            print("=" * 60)
            print(tokens["access_token"])
            print("\n" + "=" * 60)
            print("REFRESH TOKEN (действует 7 дней):")
            print("=" * 60)
            print(tokens["refresh_token"])
            print(f"\n⏱️  Срок действия access_token: {tokens['expires_in']} секунд")
            print(f"📌 Тип токена: {tokens['token_type']}")
            
            # Декодируем токен для проверки
            from jose import jwt
            payload = jwt.decode(tokens["access_token"], options={"verify_signature": False})
            print("\n📋 Payload токена:")
            for key, value in payload.items():
                if key == 'exp':
                    exp_time = datetime.fromtimestamp(value, tz=timezone.utc)
                    print(f"   {key}: {exp_time} (истекает)")
                else:
                    print(f"   {key}: {value}")
            
            return tokens
            
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            return None


async def test_file_manager_access(access_token: str, app_name: str):
    """Проверка доступа к файловому менеджеру с JWT-токеном."""
    print("\n" + "=" * 60)
    print("ПРОВЕРКА ДОСТУПА К FILE MANAGER")
    print("=" * 60)
    
    # Пробуем получить доступ к эндпоинту file manager
    # Замените на реальный эндпоинт вашего сервиса
    url = f"{FILE_MANAGER_URL}/api/v1/systems/files/"  # Примерный URL
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-App-Name": app_name
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=5.0)
            
            if response.status_code == 200:
                print(f"\n✅ Доступ разрешён! Статус: {response.status_code}")
                print(f"   Ответ: {response.text[:200]}...")
                return True
            elif response.status_code == 401:
                print(f"\n❌ Ошибка авторизации: {response.status_code}")
                print(f"   Ответ: {response.text}")
                return False
            elif response.status_code == 404:
                print(f"\n⚠️  Эндпоинт не найден (404) — возможно, сервис не запущен")
                print(f"   URL: {url}")
                return False
            else:
                print(f"\n⚠️  Статус: {response.status_code}")
                print(f"   Ответ: {response.text[:200]}")
                return False
                
        except httpx.ConnectError:
            print(f"\n⚠️  Не удалось подключиться к файловому менеджеру")
            print(f"   URL: {url}")
            print(f"   Убедитесь, что сервис запущен на порту {FILE_MANAGER_URL}")
            return False
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Регистрация app_file_manager и получение JWT-токена"
    )
    parser.add_argument(
        "--admin-token",
        type=str,
        help="JWT-токен администратора для регистрации через API"
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Прямая регистрация через БД (без админ-токена)"
    )
    parser.add_argument(
        "--app-name",
        type=str,
        default=APP_NAME,
        help=f"Имя приложения (по умолчанию: {APP_NAME})"
    )
    parser.add_argument(
        "--secret",
        type=str,
        help="Существующий app_secret для получения JWT (без регистрации)"
    )
    parser.add_argument(
        "--test-access",
        action="store_true",
        help="Тестировать доступ к файловому менеджеру после получения токена"
    )
    
    args = parser.parse_args()
    
    app_credentials = None
    
    # Этап 1: Регистрация или использование существующих данных
    if args.secret:
        print(f"\n📝 Используем существующие учётные данные для {args.app_name}")
        app_credentials = {
            "app_name": args.app_name,
            "app_secret": args.secret
        }
    elif args.direct:
        app_credentials = await register_app_direct(args.app_name, APP_DESCRIPTION)
    elif args.admin_token:
        app_credentials = await register_app_via_api(args.admin_token, args.app_name, APP_DESCRIPTION)
    else:
        print("\n❌ Выберите режим:")
        print("   --admin-token <TOKEN>  : Регистрация через API")
        print("   --direct               : Прямая регистрация через БД")
        print("   --secret <SECRET>      : Использовать существующий secret")
        print("\nПримеры:")
        print(f"   python {sys.argv[0]} --direct")
        print(f"   python {sys.argv[0]} --admin-token eyJhbGc...")
        print(f"   python {sys.argv[0]} --secret my_super_secret_token")
        sys.exit(1)
    
    if not app_credentials:
        print("\n❌ Не удалось получить учётные данные приложения")
        sys.exit(1)
    
    # Этап 2: Получение JWT-токена
    tokens = await get_jwt_token(
        app_credentials["app_name"],
        app_credentials["app_secret"]
    )
    
    if not tokens:
        print("\n❌ Не удалось получить JWT-токен")
        sys.exit(1)
    
    # Этап 3: Тестирование доступа (опционально)
    if args.test_access:
        await test_file_manager_access(
            tokens["access_token"],
            app_credentials["app_name"]
        )
    
    print("\n" + "=" * 60)
    print("ГОТОВО!")
    print("=" * 60)
    print("\n📌 Для использования в приложении:")
    print(f"   1. Сохраните app_secret: {app_credentials['app_secret'][:20]}...")
    print(f"   2. Получайте JWT-токен каждый час через /service/app/login/")
    print(f"   3. Передавайте access_token в заголовке:")
    print(f"      Authorization: Bearer {tokens['access_token'][:30]}...")
    print(f"      X-App-Name: {APP_NAME}")
    print("\n🔄 Токен истекает через 1 час — обновляйте заранее!")


if __name__ == "__main__":
    asyncio.run(main())
