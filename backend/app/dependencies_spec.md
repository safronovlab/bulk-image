# SPEC: app/dependencies.py

> **Слой**: APP  
> **Ответственность**: FastAPI Depends — авторизация, rate limiting, инъекция сервисов  
> **Соседний файл**: `dependencies.py`

---

## 1. НАЗНАЧЕНИЕ

Содержит все FastAPI dependency-функции, используемые в роутерах через `Depends()`. Обеспечивает: авторизацию (извлечение и валидация токена), rate limiting, доступ к сервисам.

---

## 2. DEPENDENCIES

### 2.1 `get_current_session`

**Тип**: FastAPI Depends  
**Используется**: во всех защищённых endpoints

**Логика:**
1. Извлечь header `Authorization` из запроса
2. Проверить формат: `Bearer <token>`. Если нет — HTTP 401
3. Извлечь token (часть после "Bearer ")
4. **Валидация формата токена:** Проверить len(token) == 32 (длина UUID hex). Токены нестандартной длины (включая строку 10MB в Authorization header) ОБЯЗАНЫ быть отклонены немедленно с HTTP 401 — ДО обращения к auth_provider. Это защита от CPU spike при парсинге мегабайтных строк
5. Вызвать auth_provider.validate_token(token)
6. Если None — HTTP 401 "Invalid or expired token"
7. Вернуть session_id

**Ответ при ошибке**: HTTPException(status_code=401, detail="...")

---

### 2.2 `get_raw_token`

**Тип**: FastAPI Depends  
**Используется**: в logout endpoint

**Логика:**
1. Извлечь header `Authorization`
2. Извлечь token
3. Вернуть token (строку)
4. Если нет — HTTP 401

---

### 2.3 `rate_limit_login`

**Тип**: FastAPI Depends
**Используется**: в POST /api/auth/login

**Определение IP клиента:** Использовать request.client.host. За reverse-proxy (nginx, Cloudflare) request.client.host возвращает IP прокси, а не клиента. Для production: использовать заголовок X-Forwarded-For с настроенным uvicorn --proxy-headers и списком trusted proxies. Без trusted proxies X-Forwarded-For подделывается тривиально.

**Логика:**
- In-memory dict: `{client_ip: [timestamp1, timestamp2, ...]}`
- При запросе: добавить текущий timestamp, удалить старше 60 сек
- Если количество > 5 за последнюю минуту — HTTP 429 "Login rate limit exceeded"
- Ключ — IP-адрес клиента (request.client.host), не session_id (сессии на этом этапе ещё нет)

---

### 2.4 `rate_limit_upload`

**Тип**: FastAPI Depends
**Используется**: в POST /api/images/upload

**Логика:**
- In-memory dict: `{session_id: [timestamp1, timestamp2, ...]}`
- При запросе: добавить текущий timestamp, удалить старше 60 сек
- Если количество > 10 за последнюю минуту — HTTP 429 "Upload rate limit exceeded"

---

### 2.5 `rate_limit_pick_color`

**Тип**: FastAPI Depends
**Используется**: в POST /api/images/{id}/pick-color

**Логика:**
- In-memory dict: `{session_id: [timestamp1, timestamp2, ...]}`
- При запросе: добавить текущий timestamp, удалить старше 60 сек
- Если количество > 60 за последнюю минуту — HTTP 429 "Pick color rate limit exceeded"
- Обоснование: каждый вызов загружает изображение в RAM (до 64MB), 60 rapid кликов/мин = 3.8GB пик без rate limit

---

### 2.6 `rate_limit_dominant_colors`

**Тип**: FastAPI Depends
**Используется**: в GET /api/images/{id}/dominant-colors

**Логика:**
- In-memory dict: `{session_id: [timestamp1, timestamp2, ...]}`
- При запросе: добавить текущий timestamp, удалить старше 60 сек
- Если количество > 20 за последнюю минуту — HTTP 429 "Dominant colors rate limit exceeded"
- Обоснование: каждый вызов запускает CPU-bound KMeans кластеризацию

---

### 2.7 `rate_limit_suggest`

**Тип**: FastAPI Depends
**Используется**: в POST /api/images/{id}/suggest-mappings

**Логика:**
- In-memory dict: `{session_id: [timestamp1, timestamp2, ...]}`
- При запросе: добавить текущий timestamp, удалить старше 60 сек
- Если количество > 10 за последнюю минуту — HTTP 429 "Suggest mappings rate limit exceeded"
- Обоснование: самая тяжёлая операция — KMeans (CPU-bound) + жадный алгоритм

---

### 2.8 `rate_limit_preview`

**Тип**: FastAPI Depends  
**Используется**: в POST /api/images/{id}/preview-replace

**Логика:**
- Аналогично rate_limit_upload, но лимит 30 запросов/мин
- HTTP 429 "Preview rate limit exceeded"

---

### 2.6 Очистка rate limit словарей

Все in-memory rate limit dict (`rate_limit_login`, `rate_limit_upload`, `rate_limit_preview`) обязаны периодически очищаться от устаревших записей, чтобы исключить неограниченный рост памяти при многократных сессиях.

**Правила:**
- При каждом вызове rate limit dependency: удалять timestamps старше 60 секунд для текущего ключа
- Периодически (при каждом вызове) проверять все ключи словаря и удалять те, чей список timestamps пуст или все timestamps старше 5 минут
- Альтернативно: подключить sweep-функцию к периодической cleanup-задаче из main.py

**Защита от OOM при DDoS:** Использовать cachetools.TTLCache (или аналог) вместо plain dict для rate limit хранилищ. Если используется plain dict — ОБЯЗАТЕЛЕН фоновый sweep ВСЕХ ключей (не только текущего) при каждом N-ном вызове (N=100). Ключи, к которым не обращаются повторно (одноразовые IP), остаются навсегда без sweep и вызывают утечку памяти.

**Ограничение масштабируемости (MVP):** Rate limiter хранит состояние in-memory. При запуске с несколькими uvicorn workers (--workers > 1) rate limit не будет общим — каждый worker ведёт свой счётчик. Для MVP (single worker) это допустимо. Для production — вынести rate limit в Redis или middleware уровня nginx.

---

### 2.7 Доступ к сервисам

Глобальные экземпляры сервисов (создаются в main.py) доступны через модульные переменные или через app.state. Dependencies возвращают их для роутеров.

Функции:
- `get_image_service()` → ImageService
- `get_job_service()` → JobService
- `get_preset_service()` → PresetService
- `get_auth_provider()` → AuthProvider

---

## 3. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Запрос с валидным Bearer token → session_id возвращается
2. Запрос без Authorization header → 401
3. Запрос с "Basic ..." → 401 (не Bearer)
4. Запрос с истёкшим token → 401
5. 6-й login за минуту с одного IP → 429
6. 11-й upload за минуту → 429
7. 31-й preview-replace за минуту → 429
