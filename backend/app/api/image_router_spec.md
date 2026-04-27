# SPEC: api/image_router.py

> **Слой**: API (тонкий HTTP-слой)  
> **Импортирует**: services/image_service (через dependencies.py)  
> **Ответственность**: HTTP-обработка всех операций с изображениями  
> **Соседний файл**: `image_router.py`

---

## 1. НАЗНАЧЕНИЕ

Роутер для всех image-related endpoints: upload, list, get, preview, original, delete, pick-color, dominant-colors, batch-analyze, preview-replace, suggest-mappings. Тонкий слой — только HTTP-логика.

---

## 2. ROUTER

Prefix: `/api/images`  
Tags: `["images"]`  
Все endpoints требуют авторизацию (Depends на auth dependency).

---

## 3. ENDPOINTS

### 3.1 `POST /api/images/upload`

**Запрос:** Multipart form-data, поле `files` — список файлов (UploadFile)

**Успешный ответ (200):** список ImageMeta

**Ошибки:**
- 400: невалидный формат, превышение лимита файлов/размера
- 401: нет авторизации
- 408: таймаут чтения файла (slowloris)

**Защита от Slowloris:** Upload endpoint принимает multipart до 500MB. Без таймаута медленный клиент занимает worker на часы. Чтение одного файла (await file.read()) ОБЯЗАНО завершиться за 60 секунд, иначе — HTTP 408. Для production рекомендуется nginx reverse proxy с client_body_timeout 60s

**Защита от OOM при upload:** Запрещено читать ВСЕ файлы в RAM одновременно. Файлы ОБЯЗАНЫ обрабатываться по одному: прочитать файл → передать в сервис → освободить. Проверять Content-Length header до начала чтения тел файлов.

**Валидация формата файлов:** НЕ доверять Content-Type от клиента. Валидация формата — исключительно по magic bytes в image_converter.load_image. При невалидном формате — HTTP 400 с указанием имени конкретного файла.

**Логика:**
1. Извлечь session_id из auth dependency
2. Обрабатывать файлы в цикле по одному: прочитать bytes одного UploadFile → передать в сервис → освободить → следующий. ЗАПРЕЩЕНО формировать полный список кортежей заранее — при 20 файлах × 50MB = 1GB пиковой RAM
3. Вызвать image_service.upload_images(session_id, files)
4. При ValueError → HTTP 400 с описанием
5. Вернуть список ImageMeta

---

### 3.2 `GET /api/images`

**Ответ (200):** список ImageMeta

**Логика:** image_service.get_images(session_id)

---

### 3.3 `GET /api/images/{image_id}`

**Ответ (200):** ImageMeta

**Ошибки:** 404 если image_id не найден

---

**Эффективная отдача файлов:** Для preview и original endpoints использовать FileResponse или генератор, читающий файл чанками по 64KB, вместо загрузки всего файла в RAM через load_file(). При 5 concurrent requests на оригиналы 4000×4000 (~5-20MB PNG) — 100MB+ RAM впустую.

### 3.4 `GET /api/images/{image_id}/preview`

**Ответ (200):** PNG-файл (Content-Type: image/png), StreamingResponse

**Логика:** image_service.get_image_preview(session_id, image_id)

**Ошибки:** 404

---

### 3.5 `GET /api/images/{image_id}/original`

**Ответ (200):** PNG-файл (Content-Type: image/png), StreamingResponse

**Логика:** image_service.get_image_original(session_id, image_id)

**Ошибки:** 404

---

### 3.6 `DELETE /api/images/{image_id}`

**Ответ (200):** `{"detail": "Image deleted"}`

**Ошибки:** 404

---

### 3.7 `POST /api/images/{image_id}/pick-color`

**Тело запроса:** PickColorRequest (`{x, y}`)

**Ответ (200):** ColorInfo (`{hex, rgb, lab}`)

**Rate limit (ОБЯЗАТЕЛЬНО):** 60 запросов/мин через dependency rate_limit_pick_color. Без rate limit: при rapid eyedropper clicks каждый вызов загружает 64MB в RAM → 60 кликов/мин × 64MB = 3.8GB пик

**Ошибки:**
- 400: координаты за пределами изображения
- 404: image_id не найден
- 429: rate limit exceeded

---

### 3.8 `GET /api/images/{image_id}/dominant-colors`

**Query params:** `count` (int, default 5, range 1-20)

**Ответ (200):** список DominantColor

**Rate limit (ОБЯЗАТЕЛЬНО):** 20 запросов/мин. Каждый вызов запускает CPU-bound KMeans кластеризацию

**Ошибки:** 404, 429

---

### 3.9 `POST /api/images/batch-analyze`

**CPU-bound защита:** batch_analyze, preview_replace и suggest_mappings ОБЯЗАНЫ выполняться через asyncio.to_thread() — KMeans кластеризация и numpy-операции блокируют event loop (10-40 секунд для batch, 50-200ms × 30 concurrent для preview-replace), парализуя healthcheck и все async endpoints. Рекомендуется HTTP-таймаут 30 секунд на уровне endpoint.

**Тело запроса:** BatchAnalyzeRequest (`{image_ids, count}`)

**Ответ (200):**
```
{
  "results": {
    "uuid-1": {"dominant_colors": [...]},
    "uuid-2": {"dominant_colors": [...]}
  }
}
```

**Ошибки:**
- 400: невалидные image_ids
- 404: один из image_id не найден

---

### 3.10 `POST /api/images/{image_id}/preview-replace`

**Тело запроса:** PreviewReplaceRequest (`{color_mappings, tolerance}`)

**Ответ (200):** PNG-файл (Content-Type: image/png), StreamingResponse — preview с применёнными заменами

**Ошибки:**
- 400: невалидные HEX или tolerance
- 404: image_id не найден

**Обязательно asyncio.to_thread():** Вызов image_service.preview_replace() на уровне роутера ОБЯЗАН быть обёрнут в asyncio.to_thread(), так как color_engine.replace_colors() — CPU-bound numpy-операция.

**Нюансы:**
- Ответ — бинарный PNG, не JSON
- Content-Disposition: inline (для отображения в браузере)
- Rate limit: 30 запросов/мин (частые подстройки tolerance)

---

### 3.11 `POST /api/images/{image_id}/suggest-mappings`

**Тело запроса:** SuggestMappingsRequest (`{target_palette}`)

**Ответ (200):** список MappingSuggestion

**Rate limit (ОБЯЗАТЕЛЬНО):** 10 запросов/мин. Вызывает KMeans (CPU-bound) + жадный алгоритм — самая тяжёлая операция после batch_analyze

**Обязательно asyncio.to_thread():** Вызов image_service.suggest_mappings() на уровне роутера ОБЯЗАН быть обёрнут в asyncio.to_thread(), так как внутренне вызывается KMeans (CPU-bound).

**Ошибки:**
- 400: невалидные HEX в target_palette
- 404: image_id не найден
- 429: rate limit exceeded

---

## 4. HTTP КОДЫ

| Код | Когда |
|-----|-------|
| 200 | Успех |
| 400 | Невалидный ввод (формат, размер, координаты) |
| 401 | Нет токена или токен невалидный |
| 404 | image_id не найден |
| 422 | Pydantic validation error (автоматически FastAPI) |
| 429 | Rate limit exceeded (через dependency) |

---

## 5. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Upload 1 PNG → 200 + ImageMeta
2. Upload JPEG → 200 + original_format="jpeg"
3. Upload 21 файл → 400
4. Upload .txt → 400
5. GET /images → список
6. GET /images/{id}/preview → PNG bytes
7. GET /images/{id}/original → PNG bytes
8. DELETE → 200
9. pick-color → ColorInfo
10. pick-color за пределами → 400
11. dominant-colors → список
12. batch-analyze → dict
13. preview-replace → PNG bytes
14. suggest-mappings → список suggestions
15. Любой endpoint без auth → 401
