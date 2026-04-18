# Инструкция по регистрации app_file_manager и получению JWT-токена

## 📋 Обзор процесса

Для доступа `app_file_manager` к файлам через `app_auth` необходимо:

1. **Зарегистрировать приложение** в `app_auth` (получить `app_secret`)
2. **Получить JWT access_token** через `/service/app/login/` (действует 1 час)
3. **Использовать токен** в заголовке `Authorization: Bearer <token>`

---

## 🔧 Способ 1: Через API (требуется токен администратора)

### Шаг 1: Регистрация приложения

```bash
curl -X POST http://localhost:8000/api/v1/auth/service/register-app/ \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "app_file_manager",
    "app_description": "Сервис управления файлами"
  }'
```

**Ответ:**
```json
{
  "success": true,
  "message": "Приложение 'app_file_manager' зарегистрировано. Токен показан один раз!",
  "app_name": "app_file_manager",
  "app_token": "<СОХРАНИТЕ_ЭТОТ_ТОКЕН>",
  "created_at": "2025-01-01T00:00:00Z",
  "created_by": "admin@example.com"
}
```

⚠️ **Важно:** `app_token` показывается только один раз! Сохраните его в безопасное место.

---

### Шаг 2: Получение JWT access_token

```bash
curl -X POST http://localhost:8000/api/v1/auth/service/app/login/ \
  -H "X-App-Name: app_file_manager" \
  -H "X-App-Secret: <СОХРАНЁННЫЙ_ТОКЕН>"
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

⏱️ `access_token` действует **30 минут** (настраивается в `ACCESS_TOKEN_EXPIRE_MINUTES`).

---

### Шаг 3: Использование токена для доступа к файлам

```bash
curl -X GET http://localhost:8001/api/v1/systems/files/ \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "X-App-Name: app_file_manager"
```

---

## 🗄️ Способ 2: Прямая регистрация через БД (если нет админ-токена)

### Требования:
- Запущенная БД PostgreSQL
- Существующий пользователь с `role_id = 3` или `4` (администратор)

### SQL-скрипт для ручной регистрации:

```sql
-- 1. Найти ID администратора
SELECT id, email FROM app_auth.users WHERE role_id IN (3, 4) LIMIT 1;

-- 2. Сгенерировать токен (в приложении используется bcrypt)
-- Вставьте результат в запрос ниже

-- 3. Добавить запись о приложении
INSERT INTO app_auth.app_credentials 
  (app_name, app_description, token_hash, is_active, created_by, expires_at)
VALUES 
  ('app_file_manager', 'Сервис управления файлами', '<HASH>', true, <ADMIN_ID>, NULL);
```

---

## 🔄 Автоматическое обновление токена

Поскольку `access_token` истекает через 30 минут, необходимо обновлять его:

### Вариант A: Повторная аутентификация с secret
```bash
# Каждый час вызывать:
curl -X POST http://localhost:8000/api/v1/auth/service/app/login/ \
  -H "X-App-Name: app_file_manager" \
  -H "X-App-Secret: <SECRET>"
```

### Вариант B: Использование refresh_token
```bash
curl -X POST http://localhost:8000/api/v1/auth/service/app/refresh/ \
  -H "Authorization: Bearer <REFRESH_TOKEN>"
```

---

## 🛠️ Использование скрипта register_app_file_manager.py

### Установка зависимостей:
```bash
pip install sqlalchemy httpx python-jose bcrypt asyncpg psycopg2-binary colorlog fastapi pydantic-settings
```

### Режимы работы:

#### 1. Прямая регистрация через БД:
```bash
python register_app_file_manager.py --direct
```

#### 2. Регистрация через API с админ-токеном:
```bash
python register_app_file_manager.py --admin-token eyJhbGciOiJIUzI1NiIs...
```

#### 3. Получить JWT с существующим secret:
```bash
python register_app_file_manager.py --secret <ВАШ_SECRET>
```

#### 4. Полная цепочка с тестом доступа:
```bash
python register_app_file_manager.py --direct --test-access
```

---

## 📁 Интеграция в app_file_manager

### Пример кода для получения и обновления токена:

```python
import httpx
from datetime import datetime, timedelta

class AuthTokenManager:
    def __init__(self, app_name: str, app_secret: str, auth_url: str):
        self.app_name = app_name
        self.app_secret = app_secret
        self.auth_url = auth_url
        self.access_token = None
        self.token_expires_at = None
    
    async def get_token(self):
        """Получить новый access_token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_url}/api/v1/auth/service/app/login/",
                headers={
                    "X-App-Name": self.app_name,
                    "X-App-Secret": self.app_secret
                }
            )
            response.raise_for_status()
            data = response.json()
            
            self.access_token = data["access_token"]
            # Устанавливаем время истечения (с запасом 5 минут)
            self.token_expires_at = datetime.now() + timedelta(
                seconds=data["expires_in"] - 300
            )
            return self.access_token
    
    async def get_valid_token(self):
        """Получить валидный токен (обновить если истекает)"""
        if not self.access_token or datetime.now() >= self.token_expires_at:
            return await self.get_token()
        return self.access_token
    
    def get_headers(self):
        """Получить заголовки для запросов"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-App-Name": self.app_name
        }

# Использование:
auth = AuthTokenManager(
    app_name="app_file_manager",
    app_secret="<SECRET>",
    auth_url="http://localhost:8000"
)

# Перед каждым запросом к файлам:
token = await auth.get_valid_token()
headers = auth.get_headers()

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8001/api/v1/systems/files/",
        headers=headers
    )
```

---

## 🔐 Безопасность

1. **Храните `app_secret` в секретах** (`.env`, Vault, AWS Secrets Manager)
2. **Не коммитьте токены в Git**
3. **Обновляйте токены заранее** (за 5 минут до истечения)
4. **Используйте HTTPS** в продакшене
5. **Регулярно ротируйте `app_secret`** через endpoint `/service/apps/{app_name}/rotate-token/`

---

## 📊 Диагностика

### Проверка статуса приложения:
```bash
curl -X GET http://localhost:8000/api/v1/auth/service/apps/ \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### Проверка токена:
```bash
curl -X POST http://localhost:8000/api/v1/auth/service/verify-token/ \
  -H "Authorization: Bearer <APP_ACCESS_TOKEN>"
```

### Просмотр логов app_auth:
```bash
tail -f /workspace/src/app_auth/logs/app.log
```

---

## ❌ Частые ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `401 Unauthorized` | Неверный secret | Проверьте `X-App-Secret` |
| `401 Token has expired` | Истёк access_token | Получите новый через `/login/` |
| `403 Application not found` | Приложение не зарегистрировано | Зарегистрируйте через `/register-app/` |
| `403 app_name mismatch` | Несовпадение имён | Проверьте `X-App-Name` и payload токена |

---

## 📞 Поддержка

При проблемах проверьте:
1. Запущен ли `app_auth` сервис
2. Доступна ли БД PostgreSQL
3. Корректность переменных окружения в `.env`
4. Логи сервиса: `/workspace/src/app_auth/logs/app.log`
