# SPEC: app/main.py

> **Слой**: APP (точка входа)  
> **Ответственность**: Создание FastAPI-приложения, CORS, подключение роутеров, lifespan events  
> **Соседний файл**: `main.py`

---

## 1. НАЗНАЧЕНИЕ

Единственная точка входа приложения. Создаёт FastAPI app, конфигурирует CORS, подключает все роутеры, запускает периодические фоновые задачи (TTL-чистка).

---

## 2. FASTAPI APP

- Заголовок: "Bulk Image Color Replacement API"
- Версия: "2.0.0"
- Описание: "Tool for bulk PNG/JPEG color replacement with design variations"

---

## 2.1 MIDDLEWARE: ГЛОБАЛЬНЫЙ ЛИМИТ РАЗМЕРА REQUEST BODY

Зарегистрировать кастомный middleware (или Starlette-совместимый) на уровне app, ограничивающий максимальный размер тела HTTP-запроса для всех JSON-эндпоинтов:

- **Лимит:** 10MB (10_485_760 байт) для всех эндпоинтов кроме multipart upload
- **Механизм:** Проверять заголовок `Content-Length` до начала чтения body. Если значение превышает лимит — немедленно вернуть HTTP 413 (Request Entity Too Large) без чтения тела запроса
- **Streaming fallback:** Если `Content-Length` отсутствует — читать body чанками и прерывать чтение с HTTP 413 при превышении лимита
- **Исключение:** Эндпоинт `POST /api/images/upload` (multipart) использует собственные лимиты из config (MAX_UPLOAD_SIZE_MB, MAX_TOTAL_UPLOAD_MB) и исключается из данного middleware

---

## 3. CORS

Конфигурация из config.py (Pydantic Settings):
- `allow_origins`: из переменной окружения `CORS_ORIGINS` (по умолчанию `["http://localhost:3000"]`). Wildcard `["*"]` запрещён при `allow_credentials=True` — это нарушает W3C CORS спецификацию и открывает CSRF-вектор
- `allow_methods`: `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers`: `["Authorization", "Content-Type"]`
- `allow_credentials`: True

---

## 4. ПОДКЛЮЧЕНИЕ РОУТЕРОВ

Подключить все 4 роутера к app:
1. `auth_router` с prefix `/api/auth`
2. `image_router` с prefix `/api/images`
3. `job_router` с prefix `/api/jobs`
4. `preset_router` с prefix `/api/presets`

---

## 5. HEALTHCHECK ENDPOINT

`GET /api/health` — непосредственно на app (не через роутер).

**Ограничение раскрытия информации:** Healthcheck НЕ требует авторизации (корректно для мониторинга). Поле version допустимо. Запрещено добавлять поля hostname, uptime, environment, internal IP или любые другие данные об инфраструктуре.

**Ответ (200):**
```
{"status": "healthy", "version": "2.0.0"}
```

---

## 6. LIFESPAN EVENTS

Использовать FastAPI lifespan context manager:

**При запуске (startup):**
1. Инициализировать file_storage (создать директории)
2. Инициализировать preset_store (загрузить/создать JSON)
3. Запустить периодическую задачу TTL-чистки
4. Зарегистрировать done-callback на asyncio task TTL-чистки с логированием — необработанные исключения и CancelledError в фоновой задаче НЕ ДОЛЖНЫ теряться молча

**При остановке (shutdown):**
1. **Сигнализировать фоновым потокам:** Установить глобальный threading.Event (stop_event) через stop_event.set(). Все BackgroundTask-потоки (run_job) ОБЯЗАНЫ проверять stop_event.is_set() после обработки каждой вариации и прерывать обработку при установленном флаге. BackgroundTask — это thread в ThreadPoolExecutor, он НЕ отменяется через asyncio.cancel()
2. Остановить периодическую задачу с таймаутом: asyncio.wait_for(task, timeout=5.0). Если задача зависла (deadlock, бесконечный compute) — не ждать дольше 5 секунд, иначе контейнер будет убит по SIGKILL
3. **Graceful drain:** Перевести ВСЕ задачи в статусе `processing` в статус `failed` с error="Server shutdown". Это предотвращает зависание задач в статусе processing навсегда при перезапуске контейнера
4. **Дождаться завершения thread pool:** Вызвать executor.shutdown(wait=True, cancel_futures=True) для корректного завершения всех фоновых потоков обработки

---

## 7. ПЕРИОДИЧЕСКАЯ ЗАДАЧА: TTL-ЧИСТКА

Запускается как asyncio task при старте приложения.

**Обязательная защита от падения задачи:** Тело цикла ОБЯЗАНО быть обёрнуто в try/except Exception с логированием. Если любой из вызовов (cleanup_expired, cleanup_expired_tokens) выбросит необработанное исключение — задача НЕ должна умирать. Исключение логируется, цикл продолжается.

**Алгоритм:**
1. Цикл: каждые 6 часов (настраиваемо)
2. Вызвать file_storage.cleanup_expired()
3. Вызвать task_store.cleanup_expired(FILE_TTL_HOURS)
4. Вызвать auth_provider.cleanup_expired_tokens()
5. Логировать количество удалённых элементов

---

## 8. СОЗДАНИЕ СЕРВИСОВ (Composition Root)

main.py является Composition Root — здесь создаются все экземпляры:
1. config = Settings() — из .env
2. stop_event = threading.Event() — флаг для graceful shutdown
3. file_storage = FileStorage(config)
4. auth_provider = AuthProvider(config)
5. task_store = TaskStore()
6. preset_store = PresetStore(config)
7. image_service = ImageService(file_storage, config)
8. job_service = JobService(file_storage, task_store, image_service, stop_event, config)
9. preset_service = PresetService(preset_store)

Экземпляры передаются в dependencies.py для FastAPI Depends.

**Защита от аварийного старта:** Вызов Settings() ОБЯЗАН быть обёрнут в try/except ValidationError. При невалидной конфигурации (.env отсутствует, AUTH_PASSWORD не соответствует требованиям) — логировать human-readable сообщение БЕЗ раскрытия путей файловой системы и завершать процесс через sys.exit(1). Необработанный ValidationError раскрывает traceback с путями ФС через uvicorn

---

## 9. НАБЛЮДАЕМОСТЬ (Observability)

**Формат логирования:** Настроить structured logging в JSON-формате (через logging.basicConfig или uvicorn --log-config). Без JSON-формата в Docker — агрегация в ELK/Loki/Grafana невозможна.

**Обязательные точки логирования:**
- Startup: факт запуска, версия, конфигурация (без секретов)
- Shutdown: факт остановки, количество принудительно завершённых задач
- Каждый cleanup cycle: количество удалённых файлов, токенов, записей
- Каждый job: start (job_id, session_id), complete (job_id, duration), fail (job_id, error class)
- Каждая неудачная попытка login: IP-адрес, username (без password), timestamp

---

## 10. КОНТЕЙНЕРИЗАЦИЯ И ДЕПЛОЙ

**Безопасность контейнера:** Dockerfile ОБЯЗАН запускать процесс от non-root пользователя. Добавить useradd с UID 1000, chown /app, директива USER перед CMD. При RCE через уязвимость Pillow/OpenCV — non-root ограничивает blast radius

**Ограничение workers:** В Dockerfile CMD ОБЯЗАН указывать --workers 1 явно. Запуск с --workers > 1 ЛОМАЕТ ВСЕ in-memory хранилища (rate limit, _tokens, _jobs, _images). Добавить --limit-concurrency 20 для защиты от перегрузки

**Фиксация зависимостей:** После первого успешного build выполнить pip freeze > requirements.lock. В Dockerfile использовать requirements.lock. requirements.txt с >= границами оставить как human-readable reference. Без фиксации pip install через месяц может подтянуть несовместимую major-версию (numpy 2.x ломает OpenCV)

**Keep-alive timeout:** В CMD добавить --timeout-keep-alive 30 для защиты от slowloris-атак

---

## 9. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. GET /api/health → 200 + healthy
2. CORS: OPTIONS-запрос с Origin → правильные заголовки
3. Все 4 роутера доступны
4. TTL-чистка: через 6 часов файлы старше 24ч удалены
