# SPEC: api/auth_router.py

> **Слой**: API (тонкий HTTP-слой)  
> **Импортирует**: services (через dependencies.py)  
> **Ответственность**: HTTP-обработка авторизации — login, logout  
> **Соседний файл**: `auth_router.py`

---

## 1. НАЗНАЧЕНИЕ

Тонкий роутер, транслирующий HTTP-запросы в вызовы auth_provider через dependencies. Не содержит бизнес-логики. Только: принять запрос → вызвать сервис → вернуть HTTP-ответ с правильным кодом.

---

## 2. ROUTER

Prefix: `/api/auth`  
Tags: `["auth"]`

---

## 3. ENDPOINTS

### 3.1 `POST /api/auth/login`

**Тело запроса:** объект LoginRequest (`{username, password}`)

**Успешный ответ (200):**
```
{
  "token": "uuid-hex-string",
  "expires_at": "ISO8601"
}
```

**Ошибки:**
- 401 Unauthorized: `{"detail": "Invalid credentials"}` — если логин/пароль неверны
- 429 Too Many Requests: `{"detail": "Login rate limit exceeded"}` — если превышен лимит 5 попыток/мин с одного IP

**Защита от brute-force:** Endpoint ОБЯЗАН использовать dependency `rate_limit_login` (максимум 5 запросов/мин по IP-адресу клиента). Без rate limiting атакующий может перебрать пароль единственного аккаунта. Для production рекомендуется экспоненциальный backoff (1s, 2s, 4s, 8s...) после 3-й неудачной попытки с одного IP и fail2ban на уровне nginx — атакующий с 10 прокси-IP получает 50 попыток/мин = 3000/час при базовом rate limit.

**Защита от timing attack:** Ответ 401 должен быть одинаковым и по содержимому, и по времени ответа для случаев «неверный логин» и «неверный пароль». Сравнение username и password в auth_provider ОБЯЗАНО использовать constant-time сравнение (hmac.compare_digest) для обоих полей.

**Защита от timing enumeration:** Роутер НЕ ДОЛЖЕН добавлять собственные проверки username/password (early return, дополнительные if-ветки). Только вызов auth_provider.authenticate(). В auth_provider оба сравнения (username + password) выполняются ВСЕГДА, даже если первое не совпало — это предотвращает timing side-channel

**Логирование auth-событий (ОБЯЗАТЕЛЬНО):** Каждая попытка логина ОБЯЗАНА логироваться: IP-адрес (request.client.host), username (без password!), результат (success/failure), timestamp. Формат: structured JSON log. При инциденте — определение времени компрометации

**Логика:**
1. Извлечь username, password из тела
2. Вызвать auth_provider.authenticate(username, password)
3. Логировать результат (success/failure) с IP и username
4. Если результат None → HTTP 401
5. Если успех → вернуть TokenResponse с кодом 200

---

### 3.2 `POST /api/auth/logout`

**Заголовки:** `Authorization: Bearer <token>` (обязательный)

**Успешный ответ (200):**
```
{"detail": "Logged out successfully"}
```

**Ошибки:**
- 401 Unauthorized: если токен невалидный или отсутствует

**Ограничение MVP (logout):** Logout инвалидирует только один токен, не все токены сессии. Если пользователь залогинился с двух вкладок (два разных token с разными session_id) — logout из одной не затрагивает другую. Для production рекомендуется функция invalidate_all_tokens().

**Логика:**
1. Извлечь token из header Authorization (через dependency)
2. Вызвать auth_provider.invalidate_token(token)
3. Вернуть 200

---

## 4. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Login с правильными credentials → 200 + token
2. Login с неправильным паролем → 401
3. Login с пустым телом → 422 (Pydantic validation)
4. Logout с валидным token → 200
5. Logout без token → 401
6. Logout с истёкшим token → 401
