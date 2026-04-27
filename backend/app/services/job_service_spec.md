# SPEC: services/job_service.py

> **Слой**: Services (Оркестрация)  
> **Импортирует**: core/color_engine, core/image_converter, core/zip_builder, infrastructure/file_storage, infrastructure/task_store  
> **Ответственность**: Создание и выполнение задач пакетной обработки (jobs), отслеживание прогресса  
> **Соседний файл**: `job_service.py`

---

## 1. НАЗНАЧЕНИЕ

Оркестрирует полный цикл пакетной обработки: парсинг запроса (Режим A или B), создание задачи в task_store, последовательная обработка каждого изображения/вариации через color_engine, сборка ZIP через zip_builder, обновление прогресса.

---

## 2. ЗАВИСИМОСТИ (инъекция)

- `file_storage` — FileStorage из infrastructure
- `task_store` — TaskStore из infrastructure
- `image_service` — ImageService (для доступа к метаданным загруженных изображений)
- `stop_event` — threading.Event, создаётся в main.py и передаётся через конструктор JobService. Устанавливается при shutdown (stop_event.set()). run_job проверяет stop_event.is_set() после каждой вариации и прерывает обработку при установленном флаге, помечая job как failed с error="Server shutdown"
- `config` — объект Settings (для JOB_TIMEOUT_SECONDS)

---

## 3. ФУНКЦИИ

### 3.1 `create_job`

**Вход:**
- `session_id`: строка UUID
- `request`: объект JobCreateRequestA ИЛИ JobCreateRequestB

**Выход:** объект JobStatus (начальный, со статусом pending)

**Алгоритм:**
1. **Определить режим** по типу request:
   - JobCreateRequestA → Режим A (индивидуальные маппинги с вариациями)
   - JobCreateRequestB → Режим B (глобальные маппинги для всех)
2. **Проверить лимит активных задач (АТОМАРНО)**: проверка лимита и создание job ОБЯЗАНЫ выполняться в одной атомарной операции под threading.Lock в task_store (метод create_job_if_limit_allows). Два concurrent POST /api/jobs могут оба пройти неатомарную проверку и оба создать job, превысив лимит 5. Если >= 5 — выбросить ValueError "Maximum concurrent jobs limit (5) reached"
3. **Нормализовать задачи**:
   - Режим A: использовать tasks as-is
   - Режим B: конвертировать в Режим A — для каждого image_id создать JobTask с одной Variation(name=variation_name, color_mappings, tolerance) из global_mappings
4. **Валидация**: проверить что все image_id существуют в image_service._images. Если нет — ValueError с перечислением отсутствующих
5. **Подсчитать total_tasks и total_variations**: total_tasks = количество уникальных image_id, total_variations = сумма всех вариаций по всем задачам
6. **Создать задачу**: task_store.create_job(session_id, total_tasks, total_variations) → job_id
7. **Вернуть** JobStatus (pending)

---

### 3.2 `run_job`

**Фоновая задача — вызывается через FastAPI BackgroundTasks.**

**Ownership-проверка в сервисе:** Проверка принадлежности job к session_id ОБЯЗАНА выполняться В СЕРВИСЕ (job_service.get_job_status, get_result_zip, delete_job), а НЕ в роутере. Router — тонкий слой без auth-логики. Проверка только в router обходима при прямом вызове service.

**Вход:**
- `job_id`: строка UUID
- `session_id`: строка UUID
- `tasks`: список нормализованных JobTask (из create_job)
- `snapshot`: frozen-структура с file paths, metadata, маппингами — копируется при create_job

**Иммутабельный snapshot (ОБЯЗАТЕЛЬНО):** run_job ОБЯЗАН работать ТОЛЬКО с путями к файлам из snapshot, НЕ обращаясь к image_service._images dict. Между create_job и началом run_job пользователь может удалить изображение через DELETE /images/{id}, что вызовет FileNotFoundError. Snapshot включает: file paths на диске, original_filename, dpi — всё что нужно для обработки

**Job timeout (ОБЯЗАТЕЛЬНО):** Конфигурируемый JOB_TIMEOUT_SECONDS (default=600). В run_job проверять elapsed_time после каждой вариации. При превышении — прерывать обработку, помечать job как failed с error="Job timeout exceeded (10 min)". При 20 файлов × 10 вариаций × 4000×4000 обработка может занять 30+ минут, блокируя thread навсегда

**Partial success (рекомендация для production):** При ошибке на одном файле — пропустить, продолжить, включить успешно обработанные файлы в ZIP. Добавить поле warnings в JobStatus для файлов с ошибками. При fail-fast потеря 70% работы критична для клиента (14 из 20 файлов обработаны, но все теряются)

**Выход:** нет (обновляет task_store по ходу выполнения)

**Управление памятью при накоплении результатов:** Рекомендуется записывать каждый обработанный PNG сразу на диск (temp dir) вместо накопления в in-memory списке. Передавать в build_zip пути к файлам вместо bytes. Пиковое потребление: 20 файлов × 3 вариации × ~5MB = ~300MB results + ~300MB ZIP = ~600MB на одну job. При 5 concurrent jobs = 3GB.

**gc.collect() — не гарантия:** gc.collect() — CPython-специфичный hint. Если numpy-массив удерживается ссылкой (view, slice, closure) — GC не соберёт его. Не полагаться на gc.collect() как единственную защиту от OOM. Использовать явное ограничение scope переменных и del.

**Sanitization ошибок:** str(exception) может содержать пути файловой системы и stack traces. ОБЯЗАТЕЛЬНО: полный traceback логировать серверно, но в поле `error` JobStatus записывать только sanitized сообщение без внутренних путей и деталей реализации.

**CPU-bound и GIL:** run_job выполняется в BackgroundTask (thread pool). color_engine.replace_colors — CPU-bound numpy операция, удерживающая GIL. Для production рекомендуется вынос CPU-bound обработки в ProcessPoolExecutor для предотвращения stalls asyncio event loop.

**Алгоритм:**
1. **Инициализация**: список результатов для ZIP = []
2. **Для каждого task (изображение):**
   a. Загрузить оригинал PNG через file_storage → bytes
   b. Конвертировать в numpy RGBA через image_converter.load_image
   c. Извлечь DPI для сохранения
   d. Получить original_filename из image_service (ImageMeta)
   e. **Для каждой variation в task.variations:**
      - Вызвать color_engine.replace_colors(rgba, variation.color_mappings, variation.tolerance)
      - Конвертировать результат в PNG bytes через image_converter.save_image_png(result_rgba, dpi)
      - Добавить в список результатов: (original_filename, variation.name, png_bytes)
      - Обновить прогресс: task_store.update_progress(job_id, processed_count)
      - processed_count += 1
   f. **Освободить память**: del rgba_array, вызвать gc.collect() после каждого изображения (защита от OOM при 20 файлов 4000x4000)
3. **Сборка ZIP**: вызвать zip_builder.build_zip(results) → zip_bytes
4. **Сохранение**: file_storage.save_result(job_id, zip_bytes) → result_path
5. **Завершение**: task_store.complete_job(job_id, result_path)
6. **Обработка ошибок**: любое исключение → логировать полный traceback серверно (logging.exception). В fail_job записывать ТОЛЬКО sanitized сообщение: "Processing failed: {type(exception).__name__}". ЗАПРЕЩЕНО включать str(exception) — может содержать пути ФС, имена модулей, stack traces, что раскрывает архитектуру приложения через GET /api/jobs/{id}

---

### 3.3 `get_job_status`

**Вход:** `job_id`: строка UUID

**Выход:** объект JobStatus или None

**Алгоритм:**
1. Получить из task_store.get_job(job_id)
2. Если None — вернуть None
3. Конвертировать внутреннюю структуру в Pydantic JobStatus
4. Если status == completed — добавить download_url = `/api/jobs/{job_id}/download`
5. Вернуть

---

### 3.4 `get_jobs`

**Вход:** `session_id`: строка UUID

**Выход:** список JobStatus

**Алгоритм:** task_store.get_jobs_by_session(session_id) → конвертировать каждый в JobStatus.

---

### 3.5 `get_result_zip`

**Вход:** `job_id`: строка UUID

**Выход:** строка result_path (путь к ZIP-файлу на диске) или None

**Zero-copy отдача:** Функция возвращает ПУТЬ к файлу, а НЕ bytes. Router использует FileResponse(result_path), который выполняет sendfile() на уровне ОС без загрузки ZIP в RAM Python-процесса. ZIP для 20 файлов × 3 вариации × 5MB = ~300MB — загрузка в RAM недопустима.

**Алгоритм:**
1. Получить job из task_store
2. Если status != completed — вернуть None
3. Проверить что result_path существует на диске (файл не удалён TTL-чисткой)
4. Вернуть result_path (строку)

---

### 3.6 `delete_job`

**Вход:** `job_id`: строка UUID

**Выход:** bool

**Алгоритм:**
1. Получить job из task_store
2. Если result_path существует — удалить через file_storage.delete_job_result(job_id)
3. Удалить из task_store.delete_job(job_id)
4. Вернуть True/False

---

## 4. УПРАВЛЕНИЕ ПАМЯТЬЮ

**Критическая секция** — обработка 20 файлов по 4000x4000:
- Один numpy RGBA массив 4000x4000 = 64MB
- 20 файлов последовательно = пик 64MB (не 1.28GB)
- После каждого файла: явный `del` переменных + `gc.collect()`
- ZIP-результат собирается в памяти (BytesIO) — пик = размер всех PNG вместе. Для 20 файлов × ~5MB PNG ≈ 100MB. Допустимо.

---

## 5. ПОСЛЕДОВАТЕЛЬНАЯ ОБРАБОТКА

Файлы обрабатываются СТРОГО ПОСЛЕДОВАТЕЛЬНО (не параллельно):
- Защита от OOM
- BackgroundTasks FastAPI запускает функцию в отдельном потоке
- Прогресс обновляется после каждой вариации (гранулярность = 1 вариация)

---

## 6. ГРАНИЧНЫЕ СЛУЧАИ

- 0 tasks: ValueError
- image_id не найден: ValueError с перечислением
- 5+ активных jobs: ValueError
- Ошибка при обработке одного файла: вся задача помечается failed (не partial success)
- Рестарт контейнера во время обработки: задача теряется (in-memory), файлы остаются на диске (чистятся по TTL)
- Пустой results (все файлы были ошибочными): ZIP будет пустым

---

## 7. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. create_job Режим A → job_id, status=pending
2. create_job Режим B → job_id, нормализация в Режим A
3. run_job 1 файл 1 вариация → status=completed, ZIP доступен
4. run_job 3 файла 2 вариации → прогресс обновляется 6 раз, ZIP содержит 6 файлов
5. run_job с несуществующим image_id → status=failed
6. get_result_zip для completed → bytes
7. get_result_zip для processing → None
8. Лимит 5 активных jobs → ValueError
9. delete_job → задача и файлы удалены
