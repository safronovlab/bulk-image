# SPEC: infrastructure/auth_provider.py

> **Слой**: Infrastructure  
> **Зависимости**: uuid, hmac, datetime (stdlib)  
> **Ответственность**: Проверка credentials из .env, управление сессионными токенами  
> **Соседний файл**: `auth_provider.py`

---

## 1. НАЗНАЧЕНИЕ

Адаптер авторизации. Единственный модуль, знающий о механизме аутентификации. Проверяет логин/пароль против переменных окружения, выдаёт и валидирует Bearer-токены.

---

## 2. КОНФИГУРАЦИЯ

Из config.py:
- `AUTH_USERNAME`: строка — логин из .env
- `AUTH_PASSWORD`: строка — пароль из .env
- `TOKEN_TTL_HOURS`: целое число (по умолчанию 24)

---

## 3. ХРАНИЛИЩЕ ТОКЕНОВ

In-memory dict: `_tokens: dict[str, TokenData]`

**Стратегия блокировки:** Использовать threading.RLock() вместо Lock (защита от accidental re-entry). Для production рекомендуется read-write lock (readers don't block readers) для validate_token, так как это read-only операция в 99% случаев. При 100+ concurrent requests threading.Lock вызывает thread starvation.

**Лимит количества токенов:** Максимальное количество одновременных токенов — 100. При превышении лимита при новом login — удалить самый старый токен (по created_at). Это защищает от OOM при brute-force атаках: cleanup_expired_tokens вызывается раз в 6 часов, и за это время можно создать миллионы записей без лимита.

**Потокобезопасность:** Все мутирующие операции с `_tokens` dict (authenticate, invalidate_token, cleanup_expired_tokens) ОБЯЗАНЫ быть защищены через threading.Lock. BackgroundTasks выполняются в отдельных потоках, что создаёт race condition при одновременном чтении/записи dict. GIL CPython — это implementation detail, на который нельзя полагаться.

**TokenData** (внутренняя структура, не Pydantic-модель):
- `session_id`: строка UUID — идентификатор сессии (используется для привязки файлов к пользователю)
- `created_at`: datetime
- `expires_at`: datetime

---

## 4. ФУНКЦИИ

**Генерация токенов:** uuid.uuid4().hex генерирует 122 бита реальной энтропии (6 бит заняты version+variant) через os.urandom — достаточно для MVP. Для production рекомендуется secrets.token_hex(32) — 256 бит чистой энтропии без структурных паттернов UUID.

### 4.1 `authenticate`

**Вход:**
- `username`: строка
- `password`: строка

**Выход:** кортеж (token: str, session_id: str, expires_at: datetime) или None при неудаче

**Алгоритм:**
1. Сравнить username с AUTH_USERNAME — через `hmac.compare_digest()` (constant-time, защита от timing side-channel). Обычное `==` раскрывает существование username через разницу во времени ответа
2. Сравнить password с AUTH_PASSWORD — через `hmac.compare_digest()` (constant-time, защита от timing attack). Для SecretStr: вызвать get_secret_value() перед сравнением
3. Если оба совпадают:
   a. Сгенерировать token = `uuid.uuid4().hex`
   b. Сгенерировать session_id = `uuid.uuid4().hex`
   c. Рассчитать expires_at = now + TOKEN_TTL_HOURS
   d. Сохранить в `_tokens[token] = TokenData(session_id, created_at, expires_at)`
   e. Вернуть (token, session_id, expires_at)
4. Если не совпадают — вернуть None

---

### 4.2 `validate_token`

**Вход:**
- `token`: строка

**Выход:** session_id (строка) или None

**Алгоритм:**
1. Найти token в `_tokens`
2. Если не найден — вернуть None
3. Если найден — проверить expires_at:
   a. Если expires_at < now — удалить из _tokens, вернуть None (токен истёк)
   b. Если expires_at >= now — вернуть session_id

---

### 4.3 `invalidate_token`

**Вход:** `token`: строка

**Выход:** bool — успешно ли инвалидирован

**Алгоритм:**
1. Если token в `_tokens` — удалить, вернуть True
2. Иначе — вернуть False

---

### 4.4 `cleanup_expired_tokens`

**Вход:** нет

**Выход:** целое число — количество удалённых токенов

**Алгоритм (двухфазное удаление — защита от RuntimeError):**
1. ПОД LOCK: Собрать список expired_keys = все ключи где expires_at < now (итерация БЕЗ удаления)
2. ПОД ТЕМ ЖЕ LOCK: Для каждого ключа из expired_keys — del _tokens[key] (удаление отдельным циклом)
3. Вернуть количество удалённых

Итерация dict + удаление элементов В ОДНОМ цикле вызывает RuntimeError: dictionary changed size during iteration. Обе фазы ОБЯЗАНЫ выполняться под одним Lock

Вызывается из периодической фоновой задачи (lifespan event в main.py).

---

## 5. БЕЗОПАСНОСТЬ

- Пароль НИКОГДА не логируется, не возвращается в ответах, не сохраняется в открытом виде кроме .env
- Сравнение пароля — ТОЛЬКО через `hmac.compare_digest()` для защиты от timing attack
- **Энтропия токенов:** Рекомендуется secrets.token_hex(32) (256 бит чистой энтропии) вместо uuid4().hex (122 бита реальной энтропии — 6 бит заняты version+variant). UUID содержит предсказуемые структурные паттерны. Для MVP допустим uuid4().hex
- **Глобальный rate limit (anti brute-force):** После 10 неудачных попыток с ЛЮБОГО IP за 5 минут — добавить sleep(2) перед ответом. IP rate limit 5/мин обходится через 10 прокси-IP (50 попыток/мин = 3000/час). Логировать каждую неудачную попытку с IP-адресом
- **Логирование auth-событий:** Каждая попытка логина (успешная и неуспешная) ОБЯЗАНА логироваться: IP-адрес, username (без password!), результат (success/failure), timestamp. Формат: structured JSON. При инциденте — определение времени компрометации

---

## 6. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Правильные credentials → возвращает token + session_id
2. Неправильный пароль → возвращает None
3. Неправильный логин → возвращает None
4. Валидация действующего token → возвращает session_id
5. Валидация истёкшего token → возвращает None, token удалён
6. Валидация несуществующего token → возвращает None
7. Инвалидация существующего token → True, повторная валидация → None
8. cleanup_expired: создать token с прошедшим expires_at → cleanup удаляет
