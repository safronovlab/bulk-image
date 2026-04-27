# SPEC: infrastructure/preset_store.py

> **Слой**: Infrastructure  
> **Зависимости**: json, os, uuid, datetime (stdlib), threading (stdlib)  
> **Ответственность**: Persistent хранилище цветовых пресетов в JSON-файле на FS  
> **Соседний файл**: `preset_store.py`

---

## 1. НАЗНАЧЕНИЕ

Хранит цветовые пресеты (палитры) клиента в JSON-файле. В отличие от task_store (in-memory), preset_store ПЕРЕЖИВАЕТ рестарт контейнера — это рабочие данные клиента для еженедельного использования.

---

## 2. ХРАНИЛИЩЕ

Файл: путь из конфигурации (по умолчанию `/app/data/presets.json`)

**Формат JSON:**
```
[
  {
    "preset_id": "uuid-hex",
    "name": "Air Jordan 1 Retro High OG Royal",
    "colors": ["#0C56A0", "#000000", "#FFFFFF"],
    "source_image_url": "https://example.com/sneaker.jpg",
    "created_at": "2026-04-27T10:00:00Z"
  },
  ...
]
```

При первом запуске, если файл не существует — создать с пустым массивом `[]`.

---

## 3. ФУНКЦИИ

### 3.1 `create_preset`

**Вход:**
- `name`: строка 1-100 символов
- `colors`: список строк HEX (1-10 элементов)
- `source_image_url`: строка или None

**Выход:** объект Preset (полный, с preset_id и created_at)

**Алгоритм:**
1. Загрузить текущий список пресетов из JSON-файла
2. Проверить уникальность имени (case-insensitive). Если дубликат — выбросить ValueError
3. Проверить лимит: максимум 100 пресетов. Если превышен — выбросить ValueError
4. Сгенерировать preset_id = uuid4().hex
5. Создать объект с created_at = now (ISO8601 UTC)
6. Добавить в список
7. Сохранить список в JSON-файл (atomic write)
8. Вернуть объект Preset

---

### 3.2 `get_all_presets`

**Вход:** нет

**Выход:** список объектов Preset

**Алгоритм:** Загрузить JSON-файл, десериализовать, вернуть список. Сортировка по created_at (новые первыми).

---

### 3.3 `get_preset`

**Вход:** `preset_id`: строка UUID

**Выход:** объект Preset или None

**Алгоритм:** Загрузить, найти по preset_id, вернуть или None.

---

### 3.4 `update_preset`

**Вход:**
- `preset_id`: строка UUID
- `name`: строка или None (не менять если None)
- `colors`: список строк HEX или None
- `source_image_url`: строка или None

**Выход:** объект Preset (обновлённый) или None (если не найден)

**Алгоритм:**
1. Загрузить список
2. Найти пресет по preset_id. Если не найден — вернуть None
3. Если name задан и отличается от текущего — проверить уникальность
4. Обновить поля, которые не None
5. Сохранить (atomic write)
6. Вернуть обновлённый объект

---

### 3.5 `delete_preset`

**Вход:** `preset_id`: строка UUID

**Выход:** bool — успешно ли удалён

**Алгоритм:**
1. Загрузить список
2. Отфильтровать — убрать запись с данным preset_id
3. Если длина не изменилась — вернуть False (не найден)
4. Сохранить (atomic write)
5. Вернуть True

---

**Защита от lost update:** threading.Lock ОБЯЗАН защищать ПОЛНЫЙ цикл read-modify-write (не только write). При concurrent requests (create + update) оба читают JSON, изменяют in-memory, записывают — последний перезатирает изменения первого. Для MVP с single worker Lock достаточен. Для multi-worker — переходить на SQLite.

**Именование backup-файлов:** При повреждённом JSON backup именуется с timestamp: `{path}.bak.{timestamp}` (ISO формат). Максимум 5 backup-файлов — при превышении удалять старейшие. Простое `{path}.bak` перезатирает предыдущие backup, теряя историю повреждений.

---

## 4. ATOMIC WRITE

Все операции записи используют паттерн atomic write для защиты от повреждения файла при сбое:

1. Записать данные во временный файл с уникальным именем: `{presets_path}.tmp.{uuid4().hex}` — уникальное имя предотвращает race condition при параллельных запросах (create + update одновременно)
2. Вызвать `os.replace(tmp_path, presets_path)` — атомарная операция на уровне ОС
3. **Durability guarantee:** После os.replace() ОБЯЗАТЕЛЕН os.fsync() на родительской директории (open(dir, O_RDONLY) + fsync). os.replace() атомарен на POSIX, но durability НЕ гарантирована на Docker overlayfs с некоторыми storage drivers. В Docker — монтировать /app/data как named volume (не bind mount) для надёжности
4. Если `os.replace` не поддерживается — fallback на `os.rename`
5. **JSON-сериализация:** Использовать json.dumps(ensure_ascii=False, allow_nan=False). allow_nan=False предотвращает запись невалидных JSON-значений (NaN, Infinity)

---

## 4.1 КЭШИРОВАНИЕ

Для снижения нагрузки на I/O (каждая CRUD-операция читает JSON с диска) ОБЯЗАТЕЛЬНО реализовать in-memory кэш:
- Десериализованный список пресетов хранится в памяти
- Read-операции (get_all, get) работают из кэша без обращения к диску
- Write-операции (create, update, delete) записывают на диск и инвалидируют кэш
- Кэш инициализируется при первом чтении или при startup

---

## 5. ПОТОКОБЕЗОПАСНОСТЬ

Использовать `threading.Lock` на всех мутирующих операциях (create, update, delete). GET-операции могут работать без блокировки (read from disk).

---

## 6. ВАЛИДАЦИЯ ИМЁН ПРЕСЕТОВ (защита от JSON-инъекций)

Поле preset.name ОБЯЗАНО проходить дополнительную валидацию на уровне модели PresetCreate (field_validator):
- Запрещены символы с кодом < 0x20 (control characters), включая null bytes (\x00)
- Запрещён символ DEL (\x7f)
- Запрещены Unicode RTL/LTR override символы (U+202A–U+202E) — могут исказить отображение имени в UI
- Pydantic-валидация 1-100 символов НЕ фильтрует эти символы по умолчанию

---

## 7. ГРАНИЧНЫЕ СЛУЧАИ

- Файл не существует при первом запуске: создать `[]`
- Файл повреждён (невалидный JSON): залогировать ошибку, создать резервную копию `{path}.bak.{timestamp}` (ISO формат, максимум 5 backup-файлов — при превышении удалять старейшие), начать с `[]`
- Дубликат имени: ValueError с сообщением "Preset with name '...' already exists"
- Лимит 100 пресетов: ValueError с сообщением "Maximum number of presets (100) reached"
- Пустой массив colors: отклоняется на уровне валидации модели (минимум 1 элемент)

---

## 7. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. create_preset → get_preset: данные совпадают
2. get_all_presets: возвращает все, сортировка по дате
3. update_preset: поля обновлены, unchanged поля сохранены
4. delete_preset: удалён, get_preset → None
5. Дубликат имени: ValueError
6. Лимит 100: ValueError
7. Файл не существует: создаётся автоматически
8. Повреждённый JSON: резервная копия, чистый старт
9. Atomic write: при сбое посередине записи оригинальный файл не повреждён
