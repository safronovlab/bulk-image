# 🏗️ ARCHITECTURE: Bulk Image Color Replacement Tool

> **Проект**: Инструмент пакетной замены цветов в PNG/JPEG-дизайнах  
> **Клиент**: Jesus Gonzalez (illcurrency.com) — sneaker-matching tee designs  
> **Бюджет**: $500 | **Дедлайн MVP**: Apr 29, 2026  
> **Статус**: ✅ Требования заморожены после Q&A + аудита  
> **Ревизия**: v2.0 (по результатам ARCHITECTURE_AUDIT.md)

---

## 1. ОБЗОР СИСТЕМЫ

### 1.1 Что делает система

Веб-инструмент, позволяющий дизайнеру sneaker-matching tees:
1. Загрузить пакет PNG/JPEG файлов (до 20 штук за раз, 300dpi, print-ready)
2. Для каждого дизайна определить цвета для замены (eyedropper по превью + ручной HEX-ввод)
3. Загрузить фото кроссовки для автоматического извлечения целевой палитры
4. Указать целевые цвета (HEX) и tolerance (ползунок)
5. Создать НЕСКОЛЬКО цветовых вариаций одного дизайна (под разные модели кроссовок)
6. Мгновенно предпросмотреть результат замены ДО запуска пакетной обработки
7. Применить один набор маппингов ко всем дизайнам одной кнопкой
8. Сохранить цветовые палитры как пресеты для еженедельного переиспользования
9. Запустить пакетную обработку в фоне
10. Скачать ZIP-архив с готовыми PNG (без потери качества, resolution, canvas size)

### 1.2 Что система НЕ делает

- НЕ конвертирует PNG ↔ SVG
- НЕ изменяет размер/resolution/canvas
- НЕ применяет recompression (output = lossless PNG)
- НЕ является многопользовательской SaaS-платформой
- НЕ хранит данные постоянно (TTL 24ч на файлы, пресеты — бессрочно)

### 1.3 Архитектурный стиль

**REST API (backend-only)** на FastAPI. Фронтенд создаётся клиентом отдельно через v0-генератор и подключается к REST API.

**Деплой**: Один Docker-контейнер с FastAPI + uvicorn.

### 1.4 Бизнес-контекст клиента

Jesus Gonzalez — владелец illcurrency.com, магазина sneaker-matching tees. Каждую неделю выходят ~2 новых модели кроссовок. Он создаёт 20+ дизайнов футболок, совпадающих по цвету с новой парой. Текущий процесс — ручная работа в Photoshop: 40-60 операций в неделю. Инструмент должен сократить это до минут, а не часов.

---

## 2. ЗАФИКСИРОВАННЫЕ АРХИТЕКТУРНЫЕ РЕШЕНИЯ

| # | Вопрос | Решение | Обоснование |
|---|--------|---------|-------------|
| 1 | Выбор цветов | Eyedropper (координаты x,y → HEX) + ручной HEX-ввод | Клиент хочет пипетку, но также знает HEX-коды кроссовок |
| 2 | Tolerance | Автоматический smart-tolerance + глобальный ползунок (0–100) | Антиалиасинг PNG требует fuzzy-match, ползунок даёт контроль |
| 3 | Frontend | Не входит в scope — клиент делает через v0 по REST API | Клиент явно указал: "фронтенд я сделаю с помощью v0" |
| 4 | Очередь задач | FastAPI BackgroundTasks + in-memory dict статусов | Single-user MVP, Redis = переусложнение |
| 5 | Деплой | Один Docker-контейнер | Клиент: "всё в одном контейнере или максимум в двух, лучше в одном" |
| 6 | Авторизация | Простая проверка логин/пароль из .env, сессия через cookie/token | Из architecture.md: "окно авторизации при входе" |
| 7 | Входные форматы | PNG + JPEG (JPEG авто-конвертация в PNG при upload) | Клиент присылал .jpeg файлы в диалоге |
| 8 | Preview замены | Мгновенный preview на уменьшенной копии ДО batch | Клиент: "send me a demo so I can see if it's what I'm looking for" |
| 9 | Вариации дизайнов | Один дизайн → N цветовых вариаций в одном job | Описание задачи: "batch export of design variations" |
| 10 | Цветовые пресеты | Сохранение палитр на FS (JSON) для переиспользования | Еженедельный workflow: 2 пары кроссовок/неделю |

---

## 3. СЛОИСТАЯ АРХИТЕКТУРА (Clean Architecture)

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND (v0)                     │
│              (Не входит в наш scope)                 │
│         Вызывает REST API через fetch/axios          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP/REST
┌──────────────────────▼──────────────────────────────┐
│                   API LAYER                          │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐           │
│  │auth_router│ │image_    │ │job_router │           │
│  │          │ │router    │ │           │           │
│  └──────────┘ └──────────┘ └───────────┘           │
│  ┌───────────┐                                      │
│  │preset_    │                                      │
│  │router     │                                      │
│  └───────────┘                                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                SERVICE LAYER                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │image_service  │ │job_service   │ │preset_service│ │
│  │(upload,       │ │(create job,  │ │(CRUD пресетов│ │
│  │ preview,      │ │ run batch,   │ │ палитр)      │ │
│  │ pick color,   │ │ track status)│ │              │ │
│  │ preview-      │ │              │ │              │ │
│  │ replace)      │ │              │ │              │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  CORE LAYER                          │
│  (Чистая бизнес-логика, ZERO внешних зависимостей)  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │color_engine   │ │color_        │ │zip_builder   │ │
│  │(pixel-level   │ │extractor     │ │(архивация    │ │
│  │ replacement   │ │(eyedropper,  │ │ результатов) │ │
│  │ с tolerance)  │ │ dominant     │ │              │ │
│  │              │ │ colors,      │ │              │ │
│  │              │ │ suggest-     │ │              │ │
│  │              │ │ mappings)    │ │              │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ │
│  ┌──────────────┐                                    │
│  │image_converter│                                   │
│  │(JPEG→PNG,     │                                   │
│  │ DPI preserve) │                                   │
│  └──────────────┘                                    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              INFRASTRUCTURE LAYER                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │file_storage   │ │auth_provider │ │task_store    │ │
│  │(локальная FS, │ │(.env login/  │ │(in-memory    │ │
│  │ TTL чистка)   │ │ password)    │ │ dict задач)  │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ │
│  ┌──────────────┐                                    │
│  │preset_store   │                                   │
│  │(JSON на FS,   │                                   │
│  │ бессрочное    │                                   │
│  │ хранение)     │                                   │
│  └──────────────┘                                    │
└─────────────────────────────────────────────────────┘
```

### Правило зависимостей

- **Core** НЕ импортирует ничего из api/, services/, infrastructure/
- **Services** импортируют Core + Infrastructure
- **API** импортирует только Services
- **Infrastructure** — адаптеры к внешнему миру (FS, .env)

---

## 4. REST API КОНТРАКТ

### 4.1 Авторизация

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/auth/login` | Принимает `{username, password}`, проверяет против .env, возвращает session token |
| `POST` | `/api/auth/logout` | Инвалидирует сессию |

**Механизм**: Bearer token в header `Authorization`. Token = UUID, хранится in-memory с TTL.

**Защита**: Все остальные endpoints требуют валидный token. Без токена → 401.

### 4.2 Загрузка изображений

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/images/upload` | Multipart upload до 20 PNG/JPEG файлов. JPEG автоконвертируются в PNG. Возвращает список `{image_id, filename, original_format, width, height, dpi, size_bytes}` |
| `GET` | `/api/images` | Список всех загруженных изображений текущей сессии |
| `GET` | `/api/images/{image_id}` | Метаданные конкретного изображения |
| `GET` | `/api/images/{image_id}/preview` | Превью PNG (уменьшенное для отображения в UI, не для обработки) |
| `GET` | `/api/images/{image_id}/original` | Оригинальный файл PNG (для eyedropper на фронте через Canvas) |
| `DELETE` | `/api/images/{image_id}` | Удалить загруженное изображение |

**Валидация upload**:
- PNG (MIME: `image/png`, magic bytes: `\x89PNG\r\n\x1a\n`)
- JPEG (MIME: `image/jpeg`, magic bytes: `\xFF\xD8\xFF`)
- Максимум 20 файлов за запрос
- Максимум 50MB на файл (300dpi print-ready может быть крупным)
- Максимум 500MB суммарно за запрос

**Конвертация JPEG → PNG при upload**:
- JPEG загружается через Pillow
- Конвертируется в RGBA (добавляется непрозрачный alpha-канал 255)
- DPI metadata сохраняется из EXIF/Pillow `info['dpi']`
- Сохраняется как lossless PNG
- В ответе `original_format: "jpeg"` для информирования фронтенда

### 4.3 Работа с цветами (Eyedropper + Analysis)

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/images/{image_id}/pick-color` | Принимает `{x, y}` координаты, возвращает `{hex, rgb, lab}` цвет пикселя |
| `GET` | `/api/images/{image_id}/dominant-colors` | K-Means кластеризация → топ-N доминантных цветов. Query param: `count` (default 5) |
| `POST` | `/api/images/batch-analyze` | Batch dominant-colors для списка изображений одним запросом |
| `POST` | `/api/images/{image_id}/suggest-mappings` | Авто-подбор маппингов по целевой палитре (LAB-расстояние) |

**Логика pick-color**:
- Координаты (x, y) берутся относительно ОРИГИНАЛЬНОГО разрешения изображения
- Фронтенд пересчитывает координаты с экранного размера Canvas в оригинальные
- Возвращает HEX, RGB и LAB представления для удобства фронтенда

**Логика dominant-colors**:
- K-Means кластеризация в LAB-пространстве (более перцептуально однородное)
- Игнорировать прозрачные пиксели (alpha < 128)
- Возвращает массив `{hex, rgb, percentage}` отсортированный по доле площади

**Логика batch-analyze** (НОВОЕ):
- Принимает `{ "image_ids": ["uuid-1", "uuid-2", ...], "count": 5 }`
- Для каждого image_id запускает dominant-colors analysis
- Возвращает `{ "results": { "uuid-1": {"dominant_colors": [...]}, "uuid-2": {...} } }`
- Позволяет проанализировать все 20 загруженных файлов одним HTTP-запросом вместо 20 отдельных

**Логика suggest-mappings** (НОВОЕ):
- Принимает `{ "target_palette": ["#1A2B3C", "#FF5500", "#FFFFFF"] }`
- Извлекает dominant colors исходного изображения
- Для каждого dominant color находит ближайший target по Delta-E (LAB)
- Возвращает массив предложений:
```
{
  "suggestions": [
    {
      "from_hex": "#CC0000",
      "to_hex": "#FF5500",
      "delta_e": 12.3,
      "confidence": 0.87,
      "from_percentage": 35.2
    },
    ...
  ]
}
```
- `confidence` = 1.0 - (delta_e / MAX_DELTA_E), отсечка < 0.3 не предлагается
- Сортировка по `from_percentage` (сначала крупные области — основные цвета дизайна)

### 4.4 Предпросмотр замены (НОВОЕ — КРИТИЧНЫЙ ENDPOINT)

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/images/{image_id}/preview-replace` | Мгновенный предпросмотр результата замены цветов на уменьшенной копии |

**Тело запроса**:
```
{
  "color_mappings": [
    {"from_hex": "#FF0000", "to_hex": "#0000FF"},
    {"from_hex": "#00FF00", "to_hex": "#FFFFFF"}
  ],
  "tolerance": 25
}
```

**Ответ**: PNG-изображение (binary, Content-Type: image/png) — preview-размер (max 800px по длинной стороне) с применёнными заменами цветов.

**Логика**:
1. Берёт preview-копию изображения (уже сгенерирована при upload, ~800px)
2. Применяет тот же алгоритм замены цветов (color_engine), что и batch-обработка
3. Возвращает результат как PNG-stream
4. Время ответа: < 0.5 сек (preview маленький, numpy vectorized)

**Зачем**: Клиент видит результат замены МГНОВЕННО, может подкрутить tolerance или поменять цвета, не дожидаясь 2-минутной batch-обработки. Устраняет страх "заплатил $500 и не знаю что получу".

### 4.5 Задачи обработки (Jobs)

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/jobs` | Создать задачу пакетной обработки |
| `GET` | `/api/jobs` | Список всех задач текущей сессии |
| `GET` | `/api/jobs/{job_id}` | Статус конкретной задачи |
| `GET` | `/api/jobs/{job_id}/download` | Скачать ZIP с результатами (доступно только при status=completed) |
| `DELETE` | `/api/jobs/{job_id}` | Отменить/удалить задачу |

**Тело POST /api/jobs — Режим A: Индивидуальные маппинги с вариациями (ОБНОВЛЕНО)**:
```
{
  "tasks": [
    {
      "image_id": "uuid-1",
      "variations": [
        {
          "name": "Jordan_Retro_Blue",
          "color_mappings": [
            {"from_hex": "#FF0000", "to_hex": "#0000FF"},
            {"from_hex": "#00FF00", "to_hex": "#FFFFFF"}
          ],
          "tolerance": 25
        },
        {
          "name": "Jordan_Bred_Red",
          "color_mappings": [
            {"from_hex": "#FF0000", "to_hex": "#CC0000"},
            {"from_hex": "#00FF00", "to_hex": "#000000"}
          ],
          "tolerance": 30
        }
      ]
    },
    {
      "image_id": "uuid-2",
      "variations": [
        {
          "name": "Jordan_Retro_Blue",
          "color_mappings": [...]
          "tolerance": 25
        }
      ]
    }
  ]
}
```

**Тело POST /api/jobs — Режим B: Глобальные маппинги для всех (НОВОЕ)**:
```
{
  "global_mappings": {
    "color_mappings": [
      {"from_hex": "#FF0000", "to_hex": "#0000FF"},
      {"from_hex": "#00FF00", "to_hex": "#FFFFFF"}
    ],
    "tolerance": 25,
    "variation_name": "Jordan_Retro_Blue"
  },
  "image_ids": ["uuid-1", "uuid-2", "uuid-3", ..., "uuid-20"]
}
```

**Правила**:
- Режимы A и B взаимоисключающие (наличие `tasks` → A, наличие `global_mappings` → B)
- Если в Режиме A у задачи одна вариация без имени → имя по умолчанию: `recolored`
- Если вариаций > 1 — имя ОБЯЗАТЕЛЬНО

**Поле tolerance**: целое число 0–100. 
- 0 = exact match (только точные пиксели данного HEX)
- 25 = рекомендуемое значение по умолчанию (покрывает антиалиасинг)
- 100 = очень широкий захват (может затронуть соседние цвета)

**Статусы задачи**:
- `pending` — задача создана, ожидает обработки
- `processing` — идёт обработка, поле `progress` показывает % (0–100)
- `completed` — готово, ZIP доступен для скачивания
- `failed` — ошибка, поле `error` содержит описание

**Структура ответа GET /api/jobs/{job_id}**:
```
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 45,
  "total_tasks": 5,
  "total_variations": 10,
  "processed_variations": 4,
  "created_at": "ISO8601",
  "completed_at": null,
  "error": null,
  "download_url": null
}
```

**ZIP-структура (ОБНОВЛЕНО)**:
- Без вариаций (1 вариация на изображение): `{original_filename}_recolored.png`
- С вариациями (>1 вариация): `{original_filename}/{variation_name}.png`
- Пример:
```
results.zip
├── skull_tee/
│   ├── Jordan_Retro_Blue.png
│   └── Jordan_Bred_Red.png
├── stay_true_tee/
│   ├── Jordan_Retro_Blue.png
│   └── Jordan_Bred_Red.png
└── voodoo_doll_tee_recolored.png    ← если только 1 вариация
```

### 4.6 Цветовые пресеты (НОВОЕ)

| Method | Endpoint | Описание |
|--------|----------|----------|
| `POST` | `/api/presets` | Создать цветовой пресет |
| `GET` | `/api/presets` | Список всех пресетов |
| `GET` | `/api/presets/{preset_id}` | Получить конкретный пресет |
| `PUT` | `/api/presets/{preset_id}` | Обновить пресет |
| `DELETE` | `/api/presets/{preset_id}` | Удалить пресет |

**Тело POST /api/presets**:
```
{
  "name": "Air Jordan 1 Retro High OG Royal",
  "colors": ["#0C56A0", "#000000", "#FFFFFF"],
  "source_image_url": "https://..."
}
```
- `name` — обязательное, уникальное, строка до 100 символов
- `colors` — обязательное, массив 1-10 HEX-кодов
- `source_image_url` — опциональное, URL фото кроссовки для визуальной привязки

**Ответ**:
```
{
  "preset_id": "uuid",
  "name": "Air Jordan 1 Retro High OG Royal",
  "colors": ["#0C56A0", "#000000", "#FFFFFF"],
  "source_image_url": "https://...",
  "created_at": "ISO8601"
}
```

**Хранение**: JSON-файл на FS (`/app/data/presets.json`). Переживает рестарт контейнера. В отличие от задач и изображений — НЕ имеет TTL, хранится бессрочно.

**UX-сценарий**: Клиент создаёт пресет "Jordan Retro Blue" с палитрой из 3 цветов. На следующей неделе, при новом дропе с такой же расцветкой — выбирает пресет из списка вместо повторного ввода hex-кодов.

### 4.7 Healthcheck

| Method | Endpoint | Описание |
|--------|----------|----------|
| `GET` | `/api/health` | Проверка работоспособности (для Docker HEALTHCHECK) |

---

## 5. CORE: АЛГОРИТМ ЗАМЕНЫ ЦВЕТОВ

### 5.1 Color Engine (ядро системы)

**Вход**: PNG-файл (numpy array RGBA), список маппингов `(from_hex, to_hex)`, tolerance (0–100).

**Алгоритм для каждого маппинга**:

1. Конвертировать исходный `from_hex` в LAB-цвет (перцептуально однородное пространство)
2. Конвертировать ВСЕ пиксели изображения в LAB-пространство (кэшировать между маппингами)
3. Для каждого пикселя рассчитать Delta-E (CIE76 — быстрый, достаточный для этого кейса) между пикселем и `from_hex`
4. Построить маску: `mask = (delta_e <= tolerance_threshold)`
   - `tolerance_threshold` = tolerance * MAX_DELTA_E / 100 (линейная шкала, MAX_DELTA_E ≈ 50)
5. Для пикселей в маске:
   - Рассчитать `blend_factor` = 1.0 - (delta_e / tolerance_threshold) — плавный переход на границах
   - Новый цвет = `lerp(original_rgb, to_rgb, blend_factor)` — это устраняет ореолы антиалиасинга
6. Применить новый цвет, СОХРАНИВ оригинальный alpha-канал (прозрачность не трогаем)

**Оптимизации**:
- Вся матрица обрабатывается через numpy vectorized operations (НЕ попиксельный цикл Python)
- LAB-конверсия через OpenCV `cvtColor` (C-оптимизированная)
- Маска — булева numpy-матрица, умножение через broadcasting

**Переиспользование для preview-replace**: Тот же самый color_engine вызывается и для preview (на уменьшенной копии ~800px) и для полной обработки (на оригинале). Единый алгоритм = предпросмотр точно соответствует финальному результату.

### 5.2 Color Extractor

**Eyedropper**: тривиально — прочитать пиксель по (x,y), вернуть HEX.

**Dominant Colors (K-Means)**:
1. Отфильтровать прозрачные пиксели (alpha < 128)
2. Subsample до максимум 50000 пикселей (для скорости)
3. K-Means в LAB-пространстве, K = запрошенное количество (default 5)
4. Для каждого кластера: центроид → HEX, количество пикселей → процент
5. Сортировать по убыванию процента

**Suggest Mappings (НОВОЕ)**:
1. Извлечь dominant colors исходного изображения (вызов dominant-colors, K=10)
2. Для каждого dominant color вычислить Delta-E до каждого цвета target_palette
3. Назначить каждому target-цвету ближайший dominant color (жадный алгоритм, без дубликатов)
4. Рассчитать confidence = 1.0 - (delta_e / MAX_DELTA_E)
5. Отфильтровать предложения с confidence < 0.3 (слишком далёкие цвета)
6. Сортировать по from_percentage (крупные области = основные цвета дизайна)

### 5.3 Image Converter (НОВОЕ)

**JPEG → PNG конверсия**:
1. Загрузить JPEG через Pillow
2. Извлечь DPI из EXIF metadata (если есть) или из Pillow `info['dpi']`
3. Конвертировать в RGBA mode (добавить alpha-канал = 255)
4. Сохранить как PNG с сохранением DPI metadata
5. Вернуть numpy array RGBA для дальнейшей обработки

**Ключевое правило**: После конвертации файл ВСЕГДА хранится и обрабатывается как PNG. Конвертация происходит ОДИН раз при upload.

### 5.4 ZIP Builder

- Создать ZIP-архив в памяти (BytesIO) или во временный файл
- **Без вариаций**: `{original_filename}_recolored.png`
- **С вариациями**: `{original_filename}/{variation_name}.png`
- PNG сохраняется БЕЗ recompression: `cv2.imwrite` с параметром `IMWRITE_PNG_COMPRESSION = 1` (минимальная, быстрая, lossless)
- Метаданные DPI сохраняются через Pillow `info['dpi']`

---

## 6. INFRASTRUCTURE

### 6.1 File Storage

- Базовая директория: `/app/data/uploads/`, `/app/data/results/`, `/app/data/previews/`
- Структура: `/{session_id}/{image_id}.png`
- **TTL-чистка**: Фоновая задача (asyncio periodic task) каждые 6 часов удаляет файлы старше 24ч
- Preview-генерация: при upload создаётся уменьшенная копия (max 800px по длинной стороне) в `/app/data/previews/`

### 6.2 Auth Provider

- Логин и пароль хранятся в `.env` файле: `AUTH_USERNAME`, `AUTH_PASSWORD`
- Пароль сравнивается через constant-time comparison (для защиты от timing attack)
- При успешном логине генерируется UUID-токен, сохраняется в in-memory dict с TTL 24ч
- Token передаётся в header: `Authorization: Bearer <token>`

### 6.3 Task Store (In-Memory)

- Python dict: `{job_id: JobStatus}`
- JobStatus содержит: status, progress, total_tasks, total_variations, processed_variations, created_at, completed_at, error, result_path
- Автоочистка: завершённые задачи старше 24ч удаляются при периодической чистке
- **Ограничение**: при рестарте контейнера все задачи теряются (приемлемо для single-user MVP)

### 6.4 Preset Store (НОВОЕ — Persistent JSON on FS)

- Файл: `/app/data/presets.json`
- Формат: JSON-массив пресетов `[{preset_id, name, colors, source_image_url, created_at}, ...]`
- **НЕ имеет TTL** — пресеты хранятся бессрочно (это рабочие данные клиента)
- Переживает рестарт контейнера (на FS, не in-memory)
- При каждой мутации (create/update/delete) — atomic write: запись во временный файл + `os.replace()`
- Максимум 100 пресетов (защита от переполнения)

---

## 7. CORS И БЕЗОПАСНОСТЬ

### 7.1 CORS

Фронтенд может работать на другом домене/порту (v0-генерированный). Необходима CORS-конфигурация:
- `allow_origins`: из `.env` переменной `CORS_ORIGINS` (по умолчанию `["*"]` для MVP)
- `allow_methods`: `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers`: `["Authorization", "Content-Type"]`
- `allow_credentials`: `true`

### 7.2 Rate Limiting

- Максимум 10 запросов upload в минуту (защита от случайного DDoS)
- Максимум 5 одновременных job на сессию
- Максимум 30 запросов preview-replace в минуту (частые подстройки tolerance)

### 7.3 Input Validation

- Файлы: проверка magic bytes (PNG: `\x89PNG\r\n\x1a\n`, JPEG: `\xFF\xD8\xFF`), а не только Content-Type
- HEX-коды: строгая валидация regex `^#[0-9A-Fa-f]{6}$`
- Координаты eyedropper: проверка bounds `0 <= x < width`, `0 <= y < height`
- Tolerance: `0 <= tolerance <= 100`, integer
- Preset name: строка 1-100 символов, trim whitespace
- Preset colors: массив 1-10 элементов, каждый — валидный HEX
- Variation name: строка 1-50 символов, только `[a-zA-Z0-9_-]` (безопасно для имён файлов в ZIP)

---

## 8. DOCKER

### Один контейнер

- **Base image**: `python:3.12-slim`
- **System deps**: `libgl1-mesa-glx`, `libglib2.0-0` (для OpenCV headless)
- **Python deps**: `fastapi`, `uvicorn`, `python-multipart`, `opencv-python-headless`, `Pillow`, `numpy`, `scikit-learn` (для K-Means)
- **Entrypoint**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **HEALTHCHECK**: `curl -f http://localhost:8000/api/health`
- **Volumes**: `/app/data` — для персистентности файлов и пресетов между рестартами
- **ENV vars**: `AUTH_USERNAME`, `AUTH_PASSWORD`, `CORS_ORIGINS`, `MAX_UPLOAD_SIZE_MB`, `FILE_TTL_HOURS`

---

## 9. СТРУКТУРА ПРОЕКТА

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, CORS, lifespan events
│   ├── config.py                  # Pydantic Settings из .env
│   ├── dependencies.py            # FastAPI Depends (auth, rate limit)
│   │
│   ├── api/                       # Routers (тонкий слой, только HTTP)
│   │   ├── __init__.py
│   │   ├── auth_router.py         # POST /login, /logout
│   │   ├── image_router.py        # POST /upload, GET /preview, /pick-color, /dominant-colors, /batch-analyze, /preview-replace, /suggest-mappings
│   │   ├── job_router.py          # POST /jobs, GET /status, /download
│   │   └── preset_router.py       # CRUD /presets (НОВОЕ)
│   │
│   ├── services/                  # Оркестрация (связывает core + infrastructure)
│   │   ├── __init__.py
│   │   ├── image_service.py       # Upload (PNG+JPEG), preview, color picking, preview-replace, suggest-mappings
│   │   ├── job_service.py         # Job creation (режим A+B, вариации), batch processing, status tracking
│   │   └── preset_service.py      # CRUD пресетов (НОВОЕ)
│   │
│   ├── core/                      # Чистая бизнес-логика (ZERO I/O)
│   │   ├── __init__.py
│   │   ├── color_engine.py        # Алгоритм замены цветов (LAB, Delta-E, masking)
│   │   ├── color_extractor.py     # Eyedropper + K-Means dominant colors + suggest-mappings
│   │   ├── image_converter.py     # JPEG→PNG конверсия с сохранением DPI (НОВОЕ)
│   │   ├── zip_builder.py         # Создание ZIP-архива (с поддержкой вариаций)
│   │   └── models.py              # Pydantic-модели (ColorMapping, JobTask, JobStatus, Variation, Preset, etc.)
│   │
│   └── infrastructure/            # Адаптеры к внешнему миру
│       ├── __init__.py
│       ├── file_storage.py        # Работа с FS (save, load, delete, TTL cleanup)
│       ├── auth_provider.py       # Проверка credentials из .env, token management
│       ├── task_store.py          # In-memory dict для статусов задач
│       └── preset_store.py        # JSON-файл на FS для пресетов (НОВОЕ)
│
├── data/                          # Runtime данные (не в git)
│   ├── uploads/
│   ├── previews/
│   ├── results/
│   └── presets.json               # Пресеты (persistent, НОВОЕ)
│
├── Dockerfile
├── .env.example
├── requirements.txt
└── README.md
```

---

## 10. ПОЛЬЗОВАТЕЛЬСКИЙ СЦЕНАРИЙ (End-to-End Flow) — ОБНОВЛЕНО

### Сценарий A: Первое использование (настройка с нуля)

**Шаг 1: Авторизация**
Пользователь открывает сайт → видит окно логина → вводит логин/пароль → `POST /api/auth/login` → получает token → сохраняет в localStorage.

**Шаг 2: Загрузка дизайнов**
Пользователь выбирает 5–20 PNG/JPEG файлов → `POST /api/images/upload` (multipart) → JPEG автоконвертируются → получает список image_id. UI показывает превью всех загруженных файлов.

**Шаг 3: Автоанализ цветов всех дизайнов**
Фронтенд вызывает `POST /api/images/batch-analyze` → получает dominant colors для каждого дизайна → отображает цветовые палитры рядом с превью.

**Шаг 4: (Опционально) Загрузка фото кроссовки для палитры**
Пользователь загружает фото кроссовки (отдельный upload или тот же endpoint) → вызывает `GET /api/images/{sneaker_id}/dominant-colors?count=3` → получает целевую палитру → сохраняет как пресет через `POST /api/presets`.

**Шаг 5: Настройка цветов**

Вариант A — Ручная настройка для каждого дизайна:
1. Фронтенд показывает превью (из `GET /api/images/{id}/original` на Canvas)
2. Пользователь кликает пипеткой по цвету на Canvas → фронтенд вычисляет (x,y) → `POST /api/images/{id}/pick-color` → получает HEX → подставляет в поле "FROM"
3. ИЛИ вводит HEX вручную в поле "FROM"
4. Вводит целевой HEX в поле "TO" (или выбирает из пресета)
5. Повторяет для 2–3 цветов в дизайне
6. Настраивает tolerance ползунком (по умолчанию 25)

Вариант B — Smart-suggest + Apply to All:
1. Пользователь выбирает пресет (или вводит target palette вручную)
2. Вызывает `POST /api/images/{id}/suggest-mappings` для первого дизайна
3. Проверяет/подтверждает предложенные маппинги
4. Нажимает "Apply to All" → используется Режим B POST /api/jobs

**Шаг 6: Предпросмотр (НОВОЕ — КЛЮЧЕВОЙ ШАГ)**
Для любого дизайна нажимает "Preview" → `POST /api/images/{id}/preview-replace` → мгновенно видит результат замены → подкручивает tolerance если нужно → preview обновляется за < 0.5 сек. Повторяет пока не удовлетворён.

**Шаг 7: Запуск обработки**
Нажимает "Process All" → `POST /api/jobs` с массивом задач (Режим A или B) → получает job_id.

**Шаг 8: Ожидание + Прогресс**
Фронтенд поллит `GET /api/jobs/{job_id}` каждые 2 секунды → показывает прогресс-бар (processed_variations / total_variations).

**Шаг 9: Скачивание**
Когда status = `completed` → кнопка "Download ZIP" → `GET /api/jobs/{job_id}/download` → браузер скачивает ZIP.

### Сценарий B: Повторное использование (следующая неделя)

1. Логин → Upload 20 новых дизайнов
2. Выбрать существующий пресет из `GET /api/presets` (например "Jordan Retro Blue")
3. `POST /api/images/{id}/suggest-mappings` → подтвердить → Apply to All
4. Preview → Process → Download
5. **Время: минуты вместо часов в Photoshop**

---

## 11. НЕФУНКЦИОНАЛЬНЫЕ ТРЕБОВАНИЯ (NFR)

| NFR | Целевое значение | Обоснование |
|-----|-------------------|-------------|
| **Latency upload** | < 3 сек на 20 файлов (локальная сеть) | UX: загрузка не должна "зависать" |
| **Preview-replace latency** | < 0.5 сек | Мгновенная обратная связь при настройке |
| **Processing speed** | < 5 сек на 1 файл (4000x4000px, 3 маппинга) | Numpy vectorized ops |
| **Batch 20 файлов** | < 2 мин полная обработка | Sequential, но без Python-loop overhead |
| **Batch 20 файлов × 3 вариации** | < 6 мин полная обработка | 60 отдельных обработок |
| **Max concurrent users** | 1 (single-tenant) | MVP, .env auth = один пользователь |
| **File retention** | 24 часа (файлы), бессрочно (пресеты) | Автоочистка файлов, пресеты — рабочие данные |
| **Availability** | 99% (VPS uptime) | Достаточно для единственного пользователя |
| **Output quality** | Pixel-perfect, lossless PNG, original DPI preserved | Критично для print-ready дизайнов |

---

## 12. РИСКИ И МИТИГАЦИИ

| Риск | Вероятность | Импакт | Митигация |
|------|-------------|--------|-----------|
| Антиалиасинг-ореолы при замене | Высокая | Высокий | LAB Delta-E + blend_factor на границах |
| OOM при 20 файлах 4000x4000 | Средняя | Высокий | Sequential processing (не параллельный), gc.collect() между файлами |
| Потеря DPI при сохранении | Средняя | Критичный | Pillow сохраняет DPI metadata, тест на это обязателен |
| Клиент не разберётся с eyedropper | Низкая | Средний | Fallback: ручной HEX-ввод + suggest-mappings |
| In-memory store теряется при рестарте | Средняя | Низкий | Приемлемо для MVP. Файлы и пресеты на FS сохраняются |
| Docker образ слишком большой (OpenCV) | Средняя | Низкий | opencv-python-headless (~50MB vs ~200MB full) |
| Клиент загружает JPEG вместо PNG | Высокая | Высокий | Авто-конвертация JPEG→PNG при upload |
| Preview не совпадает с финальным результатом | Низкая | Средний | Один и тот же color_engine для preview и batch |
| Потеря пресетов при рестарте | Низкая | Средний | JSON на FS + atomic write |
| 20 файлов × 5 вариаций = 100 обработок | Низкая | Средний | Прогресс-бар, sequential, ~10 мин допустимо |

---

## 13. ЗАВИСИМОСТИ (requirements.txt)

- `fastapi` >= 0.115
- `uvicorn[standard]` >= 0.30
- `python-multipart` >= 0.0.9
- `opencv-python-headless` >= 4.10
- `Pillow` >= 10.4
- `numpy` >= 1.26
- `scikit-learn` >= 1.5 (только для K-Means в color_extractor)
- `pydantic-settings` >= 2.4 (для .env конфигурации)

---

## 14. ПОЛНАЯ КАРТА API ENDPOINTS (24 штуки)

| # | Method | Endpoint | Назначение |
|---|--------|----------|------------|
| 1 | `POST` | `/api/auth/login` | Авторизация |
| 2 | `POST` | `/api/auth/logout` | Выход |
| 3 | `POST` | `/api/images/upload` | Upload PNG/JPEG (до 20 шт) |
| 4 | `GET` | `/api/images` | Список загруженных |
| 5 | `GET` | `/api/images/{image_id}` | Метаданные изображения |
| 6 | `GET` | `/api/images/{image_id}/preview` | Превью (уменьшенное) |
| 7 | `GET` | `/api/images/{image_id}/original` | Оригинал |
| 8 | `DELETE` | `/api/images/{image_id}` | Удалить изображение |
| 9 | `POST` | `/api/images/{image_id}/pick-color` | Eyedropper (x,y → HEX) |
| 10 | `GET` | `/api/images/{image_id}/dominant-colors` | K-Means доминантные цвета |
| 11 | `POST` | `/api/images/batch-analyze` | Batch dominant-colors |
| 12 | `POST` | `/api/images/{image_id}/suggest-mappings` | Smart auto-suggest маппингов |
| 13 | `POST` | `/api/images/{image_id}/preview-replace` | Предпросмотр замены цветов |
| 14 | `POST` | `/api/jobs` | Создать job (Режим A/B, вариации) |
| 15 | `GET` | `/api/jobs` | Список задач |
| 16 | `GET` | `/api/jobs/{job_id}` | Статус задачи |
| 17 | `GET` | `/api/jobs/{job_id}/download` | Скачать ZIP |
| 18 | `DELETE` | `/api/jobs/{job_id}` | Отменить/удалить задачу |
| 19 | `POST` | `/api/presets` | Создать пресет |
| 20 | `GET` | `/api/presets` | Список пресетов |
| 21 | `GET` | `/api/presets/{preset_id}` | Получить пресет |
| 22 | `PUT` | `/api/presets/{preset_id}` | Обновить пресет |
| 23 | `DELETE` | `/api/presets/{preset_id}` | Удалить пресет |
| 24 | `GET` | `/api/health` | Healthcheck |

---

*Документ является финальным контрактом v2.0. Все правки из ARCHITECTURE_AUDIT.md интегрированы. Следующий шаг — декомпозиция на _spec.md файлы для каждого модуля.*
