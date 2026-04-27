# SPEC: services/preset_service.py

> **Слой**: Services (Оркестрация)  
> **Импортирует**: infrastructure/preset_store  
> **Ответственность**: CRUD-операции с цветовыми пресетами (тонкая обёртка над preset_store с валидацией)  
> **Соседний файл**: `preset_service.py`

---

## 1. НАЗНАЧЕНИЕ

Тонкий сервисный слой между API-роутером пресетов и хранилищем. Добавляет бизнес-валидацию поверх CRUD-операций preset_store.

---

## 2. ЗАВИСИМОСТИ

- `preset_store` — PresetStore из infrastructure

---

## 3. ФУНКЦИИ

### 3.1 `create_preset`

**Вход:** объект PresetCreate (name, colors, source_image_url)

**Выход:** объект Preset

**Разделение ответственности валидации:** Формальная валидация (HEX regex, длина name) — ответственность Pydantic-модели PresetCreate. Сервис проверяет ТОЛЬКО бизнес-правила: дубликат имени и лимит 100 пресетов. Дублирование валидации запрещено — при расхождении правил возникнет inconsistency.

**Алгоритм:**
1. Trim whitespace в name (если не сделано Pydantic-моделью)
2. Вызвать preset_store.create_preset(name, colors, source_image_url)
4. При ValueError (дубликат имени или лимит) — пробросить наверх
5. Вернуть Preset

---

### 3.2 `get_all_presets`

**Вход:** нет

**Выход:** список Preset

**Алгоритм:** Вызвать preset_store.get_all_presets(). Вернуть результат.

---

### 3.3 `get_preset`

**Вход:** `preset_id`: строка UUID

**Выход:** Preset или None

**Алгоритм:** Вызвать preset_store.get_preset(preset_id).

---

### 3.4 `update_preset`

**Вход:** `preset_id`: строка UUID, опциональные поля: name, colors, source_image_url

**Выход:** Preset или None

**Запрет дублирования валидации:** Формальная валидация (trim, длина name, HEX regex) — ответственность Pydantic-модели на уровне router (422 при невалидных данных). Сервис проверяет ТОЛЬКО бизнес-правила (дубликат имени). Ручная ре-валидация в update_preset ЗАПРЕЩЕНА — при расхождении правил возникнет inconsistency.

**Алгоритм:**
1. Если name задан — проверить уникальность (бизнес-правило)
2. Вызвать preset_store.update_preset(...)
3. Вернуть результат

---

### 3.5 `delete_preset`

**Вход:** `preset_id`: строка UUID

**Выход:** bool

**Алгоритм:** Вызвать preset_store.delete_preset(preset_id).

---

## 4. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. create → get: данные совпадают
2. create с дубликатом имени → ValueError
3. get_all: сортировка по дате
4. update: поля обновлены
5. delete: удалён
6. get несуществующего → None
