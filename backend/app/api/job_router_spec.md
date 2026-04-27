# SPEC: api/job_router.py

> **Слой**: API (тонкий HTTP-слой)  
> **Импортирует**: services/job_service (через dependencies.py)  
> **Ответственность**: HTTP-обработка задач пакетной обработки (jobs)  
> **Соседний файл**: `job_router.py`

---

## 1. НАЗНАЧЕНИЕ

Роутер для управления задачами: создание, отслеживание прогресса, скачивание результатов, удаление. Поддерживает оба режима создания (A — индивидуальные, B — глобальные).

---

## 2. ROUTER

Prefix: `/api/jobs`  
Tags: `["jobs"]`  
Все endpoints требуют авторизацию.

---

## 3. ENDPOINTS

### 3.1 `POST /api/jobs`

**Тело запроса:** JSON — определяется по наличию ключей:
- Если есть ключ `tasks` → JobCreateRequestA (Режим A)
- Если есть ключ `global_mappings` → JobCreateRequestB (Режим B)
- Если оба или ни одного — HTTP 400

**Успешный ответ (201):** JobStatus (начальный, status=pending)

**Ошибки:**
- 400: невалидный формат, несуществующие image_id, превышение лимита jobs
- 401: нет авторизации

**CPU-bound обработка:** run_job выполняется через BackgroundTask (thread pool). Numpy-операции color_engine блокируют worker thread. Рекомендуется создать выделенный ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS) для job-processing, отдельный от default asyncio executor — иначе 5 заблокированных threads деградируют остальные async endpoints. Для production — ProcessPoolExecutor.

**Job timeout:** Максимальное время выполнения job — конфигурируемый параметр (default 600 сек). В run_job периодически проверять elapsed time и прерывать обработку при превышении, помечая job как failed с error="Job timeout exceeded".

**Иммутабельный snapshot задачи:** При создании задачи (create_job) ВСЕ необходимые данные (file paths, metadata, маппинги) ОБЯЗАНЫ быть заснапшочены как frozen-структура и переданы в run_job. Это предотвращает race condition: если пользователь удалит изображение (DELETE /images/{id}) между create_job и началом обработки — run_job продолжит работу по снапшоту.

**Логика:**
1. Извлечь session_id из auth dependency
2. Определить режим по содержимому тела
3. Валидация через Pydantic-модель
4. Вызвать job_service.create_job(session_id, request) → JobStatus (snapshot создаётся здесь)
5. Запустить job_service.run_job как BackgroundTask (получает frozen snapshot)
6. Вернуть JobStatus с кодом 201

---

### 3.2 `GET /api/jobs`

**Ответ (200):** список JobStatus

**Логика:** job_service.get_jobs(session_id)

---

### 3.3 `GET /api/jobs/{job_id}`

**Ответ (200):** JobStatus

**Ошибки:** 404

**Логика:** job_service.get_job_status(job_id). Проверить что job принадлежит session_id.

---

### 3.4 `GET /api/jobs/{job_id}/download`

**Проверка ownership (ОБЯЗАТЕЛЬНО):** Перед отдачей файла ОБЯЗАТЕЛЬНА проверка job.session_id == current_session_id. При несовпадении → 404 (НЕ 403 — чтобы не раскрывать существование чужих job). Атакующий с валидным токеном может подбирать job_id

**Эффективная отдача ZIP:** Использовать FileResponse(result_path) вместо load_file() + StreamingResponse. FileResponse выполняет sendfile() на уровне ОС без загрузки ZIP в RAM Python-процесса. ZIP для 20 файлов × 3 вариации × 5MB = ~300MB — недопустимо держать в RAM на один запрос.

**Ответ (200):** ZIP-файл, FileResponse
- Content-Type: `application/zip`
- Content-Disposition: `attachment; filename="results.zip"`
- **Cache-Control (ОБЯЗАТЕЛЬНО):** headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}. Без этих заголовков proxy/CDN может закэшировать файл с дизайнами клиента

**Ошибки:**
- 404: job не найден или не принадлежит текущей сессии
- 409 Conflict: job ещё не завершён (status != completed)

**Логика:**
1. Проверить ownership: job.session_id == current_session_id
2. Вызвать job_service.get_result_zip(job_id)
3. Если None (не completed или не найден) → проверить статус:
   - Не найден → 404
   - Не completed → 409 с сообщением "Job is still processing"
4. Если result_path → FileResponse(result_path) с Cache-Control headers — zero-copy sendfile()

---

### 3.5 `DELETE /api/jobs/{job_id}`

**Ответ (200):** `{"detail": "Job deleted"}`

**Ошибки:** 404

**Логика:** job_service.delete_job(job_id). Проверить принадлежность session_id.

---

## 4. ОПРЕДЕЛЕНИЕ РЕЖИМА ЗАПРОСА

Роутер должен корректно определить Режим A или B:

1. Принять тело как raw dict
2. Если `"tasks"` in body → валидировать как JobCreateRequestA
3. Если `"global_mappings"` in body → валидировать как JobCreateRequestB
4. Если оба ключа присутствуют → HTTP 400: "Request cannot contain both 'tasks' and 'global_mappings'"
5. Если ни одного → HTTP 400: "Request must contain either 'tasks' or 'global_mappings'"

**Запрет лишних полей (ОБЯЗАТЕЛЬНО):** В моделях JobCreateRequestA и JobCreateRequestB ОБЯЗАН быть установлен model_config = ConfigDict(extra="forbid"). Без этого Pydantic молча игнорирует дополнительные ключи (extra="ignore" по умолчанию), что позволяет атакующему внедрять неожиданные поля. Любые лишние поля → 422

---

## 5. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. POST Режим A → 201 + JobStatus(pending)
2. POST Режим B → 201 + JobStatus(pending)
3. POST с обоими ключами → 400
4. POST с пустым телом → 400
5. GET /jobs → список
6. GET /jobs/{id} → JobStatus с прогрессом
7. GET /jobs/{id}/download для completed → ZIP bytes
8. GET /jobs/{id}/download для processing → 409
9. DELETE → 200
10. Чужой job_id → 404 (не принадлежит session)
