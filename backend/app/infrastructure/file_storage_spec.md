# SPEC: infrastructure/file_storage.py

> **Слой**: Infrastructure  
> **Зависимости**: os, pathlib, asyncio, datetime (stdlib), aiofiles (опционально)  
> **Ответственность**: Работа с файловой системой — сохранение, загрузка, удаление файлов, TTL-чистка  
> **Соседний файл**: `file_storage.py`

---

## 1. НАЗНАЧЕНИЕ

Адаптер к файловой системе. Единственный модуль, который знает о путях на диске. Все остальные модули работают с bytes/numpy, а file_storage транслирует это в реальные файлы.

---

## 2. КОНФИГУРАЦИЯ

Все пути и параметры приходят из config.py (Pydantic Settings):
- `UPLOAD_DIR`: путь к директории загрузок (по умолчанию `/app/data/uploads`)
- `PREVIEW_DIR`: путь к директории превью (по умолчанию `/app/data/previews`)
- `RESULT_DIR`: путь к директории результатов (по умолчанию `/app/data/results`)
- `FILE_TTL_HOURS`: время жизни файлов в часах (по умолчанию 24)

При инициализации — создать все директории если не существуют (через `os.makedirs(..., exist_ok=True)`).

---

## 3. ФУНКЦИИ

### 3.1 `save_upload`

**Вход:**
- `session_id`: строка UUID
- `image_id`: строка UUID
- `png_bytes`: bytes — содержимое PNG-файла

**Выход:** строка — полный путь к сохранённому файлу

**Атомарная запись:** Все операции записи файлов ОБЯЗАНЫ использовать паттерн atomic write: запись во временный файл `{image_id}.png.tmp` → `os.replace(tmp, final)` → финальное имя. При crash посередине записи частично записанный .tmp файл не будет виден под основным именем, и load_file не вернёт битые данные.

**Очистка осиротевших tmp-файлов:** В cleanup_expired ОБЯЗАТЕЛЬНО сканировать и удалять `*.tmp` файлы старше 1 часа во ВСЕХ директориях (UPLOAD_DIR, PREVIEW_DIR, RESULT_DIR). При crash между записью tmp и os.replace — tmp-файл остаётся на диске навсегда.

**Проверка свободного места:** Перед записью ОБЯЗАТЕЛЬНА проверка доступного места через shutil.disk_usage(). Если свободно менее MAX_TOTAL_UPLOAD_MB × 2 — отказывать с ошибкой (HTTP 507 Insufficient Storage на уровне API). Это early rejection heuristic, НЕ гарантия — между проверкой и записью место может быть занято (TOCTOU). Поэтому ОБЯЗАТЕЛЬНО также перехватывать OSError/IOError при записи как fallback.

**Алгоритм:**
1. Создать директорию `{UPLOAD_DIR}/{session_id}/` если не существует
2. Путь файла: `{UPLOAD_DIR}/{session_id}/{image_id}.png`
3. Записать png_bytes во временный файл `{image_id}.png.tmp` (binary mode)
4. Атомарно переместить: os.replace(tmp_path, final_path)
5. Вернуть путь

---

### 3.2 `save_preview`

**Вход:**
- `session_id`: строка UUID
- `image_id`: строка UUID
- `png_bytes`: bytes — содержимое preview PNG

**Выход:** строка — полный путь

**Алгоритм:** Аналогично `save_upload`, но в `PREVIEW_DIR`.

---

### 3.3 `save_result`

**Вход:**
- `job_id`: строка UUID
- `zip_bytes`: bytes — содержимое ZIP-файла

**Выход:** строка — полный путь к ZIP

**Атомарная запись:** Аналогично save_upload и save_preview, save_result ОБЯЗАН использовать паттерн atomic write: запись в `results.zip.tmp` → `os.replace(tmp, final)`. При crash/OOM-kill во время записи ZIP (до 300MB) частично записанный файл не будет виден под основным именем.

**Алгоритм:**
1. Создать директорию `{RESULT_DIR}/{job_id}/` если не существует
2. Путь: `{RESULT_DIR}/{job_id}/results.zip`
3. Записать bytes во временный файл `results.zip.tmp` (binary mode)
4. Атомарно переместить: os.replace(tmp_path, final_path)
5. Вернуть путь

---

### 3.4 `load_file`

**Вход:**
- `file_path`: строка — полный путь к файлу

**Выход:** bytes — содержимое файла

**Алгоритм:**
1. Проверить что файл существует. Если нет — выбросить FileNotFoundError
2. Проверить что путь находится внутри одной из разрешённых директорий (UPLOAD_DIR, PREVIEW_DIR, RESULT_DIR) — защита от path traversal
3. Прочитать файл в binary mode
4. Вернуть bytes

---

### 3.5 `delete_file`

**Вход:** `file_path`: строка

**Выход:** bool — успешно ли удалено

**Алгоритм:**
1. Проверить путь на path traversal (как в load_file)
2. Если файл существует — удалить, вернуть True
3. Если не существует — вернуть False

---

### 3.6 `delete_session_files`

**Вход:** `session_id`: строка UUID

**Выход:** целое число — количество удалённых файлов

**Алгоритм:**
1. Удалить директорию `{UPLOAD_DIR}/{session_id}/` рекурсивно (shutil.rmtree)
2. Удалить директорию `{PREVIEW_DIR}/{session_id}/` рекурсивно
3. Вернуть общее количество удалённых файлов

**Безопасность concurrent access:** Перед rmtree проверять нет ли активных jobs (status=processing) для данного session_id. Использовать shutil.rmtree(path, ignore_errors=True) для resilience — при concurrent access run_job может записывать в момент удаления.

---

### 3.7 `delete_job_result`

**Вход:** `job_id`: строка UUID

**Выход:** bool

**Алгоритм:** Удалить `{RESULT_DIR}/{job_id}/` рекурсивно.

---

### 3.8 `get_upload_path`

**Вход:** `session_id`, `image_id`

**Выход:** строка — полный путь (без проверки существования)

Утилита для формирования пути.

---

### 3.9 `get_preview_path`

Аналогично `get_upload_path`, но для PREVIEW_DIR.

---

### 3.10 `cleanup_expired`

**Фоновая задача TTL-чистки.**

**Вход:** нет (использует FILE_TTL_HOURS из конфигурации)

**Выход:** целое число — количество удалённых директорий

**Алгоритм:**
1. Для каждой из трёх директорий (UPLOAD_DIR, PREVIEW_DIR, RESULT_DIR):
2. Перебрать все поддиректории (session_id / job_id)
3. Для каждой — проверить время модификации самого нового файла внутри
4. Если все файлы старше FILE_TTL_HOURS — удалить всю директорию рекурсивно
5. Логировать количество удалённых
6. Вернуть общее количество

---

## 4. БЕЗОПАСНОСТЬ

- **Path Traversal Protection**: все функции load/delete проверяют что результирующий путь находится внутри разрешённой базовой директории. ОБЯЗАТЕЛЬНО использовать `Path.resolve()` для обоих путей (проверяемого и базового), затем проверять через `resolved_path.is_relative_to(base_resolved)` (Python 3.9+). Проверка через `str.startswith()` ЗАПРЕЩЕНА — она ненадёжна (пример: base = `/app/data/uploads`, path = `/app/data/uploads_evil/../../etc/passwd` пройдёт startswith, но не пройдёт is_relative_to)
- **Защита от symlink-атак:** В load_file ПОСЛЕ resolve() ОБЯЗАТЕЛЬНА проверка os.path.islink() на финальном пути. Symlink внутри upload dir может указывать на /etc/passwd — resolve() и is_relative_to пройдут, но файл будет прочитан из произвольного расположения. Запрещать чтение symlink-ов. В Docker — запуск от non-root user (USER 1000) минимизирует blast radius
- **Максимальный размер файла**: проверка на уровне API (не здесь), но file_storage НЕ загружает в память файлы больше 500MB
- **Защита от исчерпания диска:** В save_upload и save_preview ОБЯЗАТЕЛЬНА проверка свободного места через shutil.disk_usage(). Если свободно менее 1GB — отказывать с ошибкой (HTTP 507 на уровне API). Docker volume без quota позволяет заполнить диск полностью (5 сессий × 20 файлов × 50MB = 5GB + previews + результаты) до следующей TTL-чистки через 6 часов
- **Безопасность concurrent cleanup:** cleanup_expired ОБЯЗАН проверять наличие активных jobs (status=processing) для session_id перед удалением session-директории через task_store.count_active_jobs(). При concurrent access run_job может записывать результат в момент rmtree. Использовать shutil.rmtree(path, ignore_errors=True) для resilience

---

## 5. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. save_upload + load_file: сохранить bytes → загрузить → bytes совпадают
2. delete_file существующего: возвращает True, файл удалён
3. delete_file несуществующего: возвращает False
4. Path traversal: попытка load `../../etc/passwd` → ошибка
5. cleanup_expired: создать файл со старой датой → cleanup удаляет
6. cleanup_expired: свежий файл → cleanup НЕ удаляет
