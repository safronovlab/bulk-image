# SPEC: services/image_service.py

> **Слой**: Services (Оркестрация)  
> **Импортирует**: core/image_converter, core/color_engine, core/color_extractor, infrastructure/file_storage  
> **Ответственность**: Оркестрация всех операций с изображениями — upload, preview, eyedropper, dominant colors, preview-replace, suggest-mappings, batch-analyze  
> **Соседний файл**: `image_service.py`

---

## 1. НАЗНАЧЕНИЕ

Связующее звено между API-роутерами и core/infrastructure. Принимает высокоуровневые запросы от роутеров, координирует вызовы к core-модулям и file_storage. Не содержит бизнес-логики обработки цветов — только оркестрацию.

---

## 2. ЗАВИСИМОСТИ (инъекция)

Сервис принимает экземпляры зависимостей через конструктор или параметры функций:
- `file_storage` — экземпляр FileStorage из infrastructure
- Функции из core вызываются как чистые функции (без состояния)

---

## 3. ВНУТРЕННЕЕ ХРАНИЛИЩЕ

In-memory dict для метаданных загруженных изображений:
- `_images: dict[str, ImageMeta]` — ключ = image_id
- **Потокобезопасность:** _images dict ОБЯЗАН быть защищён через threading.Lock на ВСЕХ read/write операциях. dict модифицируется из upload (main thread) и читается из run_job (background thread) — без Lock возможен torn read
- **Защита от IDOR (Insecure Direct Object Reference):** Привязка к сессии: каждый ImageMeta ОБЯЗАН хранить session_id явно. Реализовать ownership-проверку как единый helper `_verify_ownership(session_id, image_id)` и вызывать его ПЕРВОЙ строкой в КАЖДОЙ функции (get_image, get_image_original, get_image_preview, delete_image, pick_color, get_dominant_colors, preview_replace, suggest_mappings). Без проверки — атакующий с валидным токеном получает доступ к чужим изображениям через подбор UUID

**Устойчивость к рестартам:** При рестарте контейнера in-memory метаданные теряются, хотя файлы на диске остаются. Рекомендуется при startup восстанавливать `_images` сканированием UPLOAD_DIR, либо хранить метаданные в JSON-файле (как preset_store). Это предотвращает появление «файлов-сирот» и потерю загруженных изображений.

---

## 4. ФУНКЦИИ

### 4.1 `upload_images`

**Вход:**
- `session_id`: строка UUID
- `files`: список кортежей (filename: str, content: bytes) — до 20 файлов

**Выход:** список объектов ImageMeta

**Rollback при частичном сбое:** Цикл обработки файлов ОБЯЗАН быть обёрнут в try/except. При ошибке на любом файле (ValueError, IOError) — вызвать file_storage.delete_file() для ВСЕХ уже сохранённых файлов текущего batch (оригиналы + preview), удалить записи из _images, затем пробросить ValueError. Без rollback: при 20 запросах с 14 успешными + 1 битым файлом = 280 файлов-сирот × 50MB = 14GB мёртвого хранения до TTL-чистки (24ч).

**Алгоритм:**
1. Проверить количество файлов: 1-20. Если > 20 — выбросить ValueError
2. Рассчитать суммарный размер: если > 500MB — выбросить ValueError
3. Инициализировать список saved_ids = [] (для rollback)
4. **Для каждого файла (в блоке try):**
   a. Проверить размер: если > 50MB — выбросить ValueError с именем файла
   b. Обрезать filename до 255 символов (защита от oversized filename)
   c. Вызвать `image_converter.load_image(content)` — определяет формат, конвертирует в RGBA numpy, извлекает DPI
   d. Если формат не определён (None) — выбросить ValueError с именем файла
   e. Сгенерировать image_id = uuid4().hex
   f. Вызвать `image_converter.save_image_png(rgba_array, dpi)` — получить PNG bytes
   g. Вызвать `file_storage.save_upload(session_id, image_id, png_bytes)` — сохранить оригинал
   h. Вызвать `image_converter.create_preview(rgba_array, max_size=800)` — создать preview numpy
   i. Вызвать `image_converter.save_image_png(preview_array, dpi)` — получить preview PNG bytes
   j. Вызвать `file_storage.save_preview(session_id, image_id, preview_bytes)` — сохранить preview
   k. Создать объект ImageMeta с метаданными (image_id, filename, original_format, width, height, dpi, size_bytes, uploaded_at)
   l. Сохранить в `_images[image_id]`
   m. Добавить image_id в saved_ids
5. **При исключении (блок except):**
   a. Для каждого image_id в saved_ids — вызвать file_storage.delete_file для оригинала и preview
   b. Удалить все saved_ids из _images
   c. Пробросить ValueError с описанием ошибки
6. Вернуть список ImageMeta

---

### 4.2 `get_images`

**Вход:** `session_id`: строка UUID

**Выход:** список ImageMeta

**Алгоритм:** Отфильтровать `_images` по session_id (проверить что файл существует на диске). Сортировать по uploaded_at.

---

### 4.3 `get_image`

**Вход:** `image_id`: строка UUID

**Выход:** ImageMeta или None

---

### 4.4 `get_image_original`

**Вход:** `session_id`: строка, `image_id`: строка

**Выход:** bytes (PNG-файл)

**Алгоритм:**
1. Получить путь через file_storage.get_upload_path
2. Загрузить через file_storage.load_file
3. Вернуть bytes

---

### 4.5 `get_image_preview`

**Вход:** `session_id`: строка, `image_id`: строка

**Выход:** bytes (preview PNG)

**Алгоритм:** Аналогично get_image_original, но из preview directory.

---

### 4.6 `delete_image`

**Вход:** `session_id`: строка, `image_id`: строка

**Выход:** bool

**Алгоритм:**
1. Удалить оригинал через file_storage.delete_file
2. Удалить preview через file_storage.delete_file
3. Удалить из `_images`
4. Вернуть True/False

---

### 4.7 `pick_color`

**Вход:** `session_id`: строка, `image_id`: строка, `x`: int, `y`: int

**Выход:** объект ColorInfo

**Оптимизация памяти (ОБЯЗАТЕЛЬНО):** Загрузка оригинала 4000×4000 = 64MB RAM для одного пикселя расточительна. При 30 rapid eyedropper кликах/мин (pick-color НЕ rate-limited в текущей спеке) — 30 × 64MB = 1.9GB/мин, GC может не успеть. ОБЯЗАТЕЛЬНО использовать один из двух подходов:
- Загружать ТОЛЬКО preview (800px, ~2.5MB) и пересчитывать координаты: x_preview = x * preview_w / original_w, y_preview = y * preview_h / original_h
- Использовать Pillow Image.getpixel() без конвертации в numpy

**Rate limit:** pick-color ОБЯЗАН быть rate-limited: 60 запросов/мин (описать в dependencies_spec.md)

**Алгоритм:**
1. Загрузить preview PNG (или оригинал с оптимизацией) через file_storage.load_file
2. Конвертировать в numpy RGBA через image_converter.load_image (или использовать Pillow getpixel)
3. Пересчитать координаты если используется preview
4. Проверить bounds: 0 <= x < width, 0 <= y < height. Если нет — ValueError
5. Вызвать color_extractor.pick_color(rgba_array, x, y)
6. Вернуть ColorInfo

---

### 4.8 `get_dominant_colors`

**Вход:** `session_id`: строка, `image_id`: строка, `count`: int (default 5)

**Выход:** список DominantColor

**Алгоритм:**
1. Загрузить оригинал → numpy RGBA
2. Вызвать color_extractor.extract_dominant_colors(rgba_array, count)
3. Вернуть результат

---

### 4.9 `batch_analyze`

**Вход:** `session_id`: строка, `image_ids`: список строк, `count`: int (default 5)

**Выход:** dict[str, list[DominantColor]] — image_id → dominant colors

**Защита от IDOR:** Ownership-проверка ОБЯЗАТЕЛЬНА для КАЖДОГО image_id из списка перед началом обработки. Один чужой UUID → HTTP 403 на весь запрос. batch_analyze принимает произвольные UUID, и без проверки атакующий с валидным токеном может получить цветовую информацию чужих изображений

**Алгоритм:**
1. Для каждого image_id:
   a. Проверить ownership через _verify_ownership(session_id, image_id) — ОБЯЗАТЕЛЬНО
   b. Проверить что image_id существует в _images
   c. Вызвать get_dominant_colors(session_id, image_id, count)
   d. Сохранить результат
2. Вернуть словарь

---

### 4.10 `preview_replace`

**Вход:** `session_id`: строка, `image_id`: строка, `color_mappings`: список ColorMapping, `tolerance`: int

**Выход:** bytes (PNG preview с применёнными заменами)

**Алгоритм:**
1. Загрузить PREVIEW (не оригинал!) через file_storage → bytes
2. Конвертировать в numpy RGBA
3. Вызвать color_engine.replace_colors(preview_rgba, color_mappings, tolerance)
4. Конвертировать результат обратно в PNG bytes (через image_converter.save_image_png, dpi=None для preview)
5. Вернуть bytes

**Критически важно**: Обрабатывается PREVIEW (уменьшенное ~800px), а не оригинал. Это даёт скорость < 0.5 сек.

---

### 4.11 `suggest_mappings`

**Вход:** `session_id`: строка, `image_id`: строка, `target_palette`: список строк HEX

**Выход:** список MappingSuggestion

**Алгоритм:**
1. Загрузить оригинал → numpy RGBA
2. Вызвать color_extractor.suggest_mappings(rgba_array, target_palette)
3. Вернуть результат

---

## 5. УПРАВЛЕНИЕ ПАМЯТЬЮ

- При загрузке 20 файлов по 4000x4000 — каждый numpy-массив ~64MB (4000*4000*4 bytes)
- НЕЛЬЗЯ держать все 20 в памяти одновременно
- upload_images обрабатывает файлы ПОСЛЕДОВАТЕЛЬНО, каждый раз после сохранения на диск — numpy-массив выходит из scope и освобождается GC
- Для pick_color, dominant_colors, preview_replace — загружается ОДИН файл за раз

---

## 6. ГРАНИЧНЫЕ СЛУЧАИ

- 0 файлов в upload: ValueError
- Файл > 50MB: ValueError с именем файла
- Суммарный размер > 500MB: ValueError
- Невалидный формат (не PNG/JPEG): ValueError с именем файла
- image_id не найден: возвращается None или выбрасывается ошибка (на усмотрение реализации)
- Координаты eyedropper за границами: ValueError

---

## 7. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Upload 1 PNG → ImageMeta с корректными метаданными
2. Upload 1 JPEG → ImageMeta с original_format="jpeg"
3. Upload 21 файл → ValueError
4. Upload файл > 50MB → ValueError
5. Upload невалидный файл (.txt) → ValueError
6. pick_color на известном пикселе → корректный HEX
7. preview_replace → PNG bytes, размер < оригинала (preview)
8. batch_analyze 3 файла → dict с 3 ключами
9. suggest_mappings → список предложений с confidence
