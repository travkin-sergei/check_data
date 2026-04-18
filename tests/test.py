import requests

url = "http://127.0.0.1:8000/api/v1/auth/login/"
data = {
    "email": "user@example.com",
    "password": "string"
}

# Делаем запрос
response = requests.post(url, json=data)

print("--- ЗАГОЛОВКИ ОТВЕТА (СЮДА СЕРВЕР СПРЯТАЛ ТОКЕН) ---")
# Выводим все заголовки, особенно нас интересует Set-Cookie
for key, value in response.headers.items():
    if 'Cookie' in key or 'Auth' in key:
        print(f"{key}: {value}")

print("\n--- ИЗВЛЕЧЕННЫЙ ТОКЕН ---")
# Пытаемся достать токен из куки автоматически
token = response.cookies.get("user_access_token")

if token:
    print(f"✅ ВОТ ОН: {token}")
    print("\nКак использовать в другом приложении:")
    print(f"Заголовок: Authorization: Bearer {token}")
    print(f"ИЛИ Заголовок: Cookie: user_access_token={token}")
else:
    print("❌ Токен не найден в куках. Проверьте вывод заголовков выше.")
    print("Возможно, имя куки отличается (например, access_token).")