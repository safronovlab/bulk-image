# SPEC: infrastructure/task_store.py

> **Слой**: Infrastructure  
> **Зависимости**: uuid, datetime (stdlib)  
> **Ответственность**: In-memory хранилище статусов задач обработки (jobs)  
> **Соседний файл**: `task_store.py`

---

## 1. НАЗНАЧЕНИЕ

Хранит статусы всех задач пакетной обработки в оперативной памяти (Python dict). Обеспечивает CRUD-операции и отслеживание прогресса. При рестарте контейнера данные теряются — приемлемо для single-user MVP.

**Восстановление после рестарта:** При startup рекомендуется сканировать RESULT_DIR и создавать «восстановленные» записи для существующих ZIP-файлов с status=completed. Без этого файлы результатов остаются на диске как «сироты» без связи job_id → result.zip. Альтернатива — хранить task_store в JSON-файле (как preset_store).

---

## 2. ХРАНИЛИЩЕ

In-memory dict: `_jobs: dict[str, JobStatusInternal]`

**JobStatusInternal** (внутренняя структура):
- `job_id`: строка UUID
- `session_id`: строка UUID (привязка к сессии пользователя)
- `status`: строка из перечисления (`pending`, `processing`, `completed`, `failed`)
- `progress`: целое число 0–100
- `total_tasks`: целое число (количество изображений)
- `total_variations`: целое число (общее количество вариаций)
- `processed_variations`: целое число
- `created_at`: datetime
- `completed_at`: datetime или None
- `error`: строка или None
- `result_path`: строка или None (путь к ZIP-файлу на диске)

---

## 3. ФУНКЦИИ

### 3.1 `create_job`

**Вход:**
- `session_id`: строка UUID
- `total_tasks`: целое число
- `total_variations`: целое число

**Выход:** строка — job_id (сгенерированный UUID)

**Алгоритм:**
1. **Проверка лимита записей:** Если len(_jobs) >= 1000 — удалить oldest completed/failed записи для освобождения места. Без лимита _jobs dict растёт неограниченно (cleanup каждые 6 часов, за это время могут накопиться тысячи записей)
2. Сгенерировать job_id = uuid4().hex
3. Создать JobStatusInternal со статусом `pending`, progress=0, processed_variations=0
4. Сохранить в `_jobs[job_id]`
5. Вернуть job_id

---

### 3.2 `get_job`

**Вход:**
- `job_id`: строка UUID

**Выход:** JobStatusInternal или None

**Алгоритм:** Вернуть `_jobs.get(job_id)` или None.

---

### 3.3 `get_jobs_by_session`

**Вход:**
- `session_id`: строка UUID

**Выход:** список JobStatusInternal

**Алгоритм:** Отфильтровать все записи где `session_id` совпадает. Сортировать по `created_at` (новые первыми).

---

### 3.4 `update_progress`

**Вход:**
- `job_id`: строка UUID
- `processed_variations`: целое число

**Выход:** bool — успешно ли обновлено

**Алгоритм:**
1. Найти job в `_jobs`
2. Если не найден — вернуть False
3. Обновить `processed_variations`
4. Обновить `status` → `processing` (если ещё не)
5. Рассчитать `progress` = round(processed_variations / total_variations * 100)
6. Вернуть True

**Защита от overflow прогресса:** update_progress ОБЯЗАН применять min(processed_variations, total_variations) перед пересчётом progress. Assertion: processed_variations <= total_variations. Без этого баг в run_job может выдать progress = 150%, сломав фронтенд.

---

### 3.5 `complete_job`

**Вход:**
- `job_id`: строка UUID
- `result_path`: строка — путь к ZIP

**Выход:** bool

**Алгоритм:**
1. Найти job, обновить:
   - `status` = `completed`
   - `progress` = 100
   - `processed_variations` = `total_variations`
   - `completed_at` = now
   - `result_path` = result_path
2. Вернуть True (или False если не найден)

---

### 3.6 `fail_job`

**Вход:**
- `job_id`: строка UUID
- `error_message`: строка

**Выход:** bool

**Алгоритм:**
1. Найти job, обновить:
   - `status` = `failed`
   - `completed_at` = now
   - `error` = error_message
2. Вернуть True (или False если не найден)

---

### 3.7 `delete_job`

**Вход:** `job_id`: строка UUID

**Выход:** bool

**Алгоритм:** Удалить из `_jobs` если существует.

---

### 3.8 `count_active_jobs`

**Вход:** `session_id`: строка UUID

**Выход:** целое число — количество активных задач (pending + processing)

**Алгоритм:** Подсчитать записи с данным session_id и статусом pending или processing.

Используется для rate limiting (максимум 5 одновременных job на сессию).

---

### 3.9 `cleanup_expired`

**Вход:** `ttl_hours`: целое число

**Выход:** целое число — количество удалённых записей

**Алгоритм:**
1. Текущее время = now
2. Для каждой записи: если `completed_at` (или `created_at` для pending) старше ttl_hours — удалить
3. Вернуть количество удалённых

---

## 4. ПОТОКОБЕЗОПАСНОСТЬ

Использование threading.Lock ОБЯЗАТЕЛЬНО на ВСЕХ операциях с `_jobs` dict (и чтение, и запись). BackgroundTask (run_job) вызывает update_progress из отдельного потока одновременно с GET /jobs/{id} из main thread. Без Lock — data race, возможно чтение частично обновлённого JobStatusInternal (torn read).

**Защита от зависших задач:** В cleanup_expired ОБЯЗАТЕЛЬНО добавить обработку зависших задач:
- Задачи в статусе `processing` старше 2×TTL — принудительно удалять
- Задачи в статусе `pending` старше 1 часа без перехода в processing — помечать как failed с error="Stale pending job"

---

## 5. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. create_job → get_job: данные совпадают
2. update_progress: processed_variations обновляется, progress пересчитывается
3. complete_job: status=completed, progress=100, result_path задан
4. fail_job: status=failed, error задан
5. get_jobs_by_session: возвращает только задачи данной сессии
6. count_active_jobs: pending+processing подсчитаны
7. cleanup_expired: старые удалены, свежие остались
8. delete_job: запись удалена
