# SPEC: core/image_converter.py

> **Слой**: Core  
> **Зависимости**: Pillow (PIL), numpy  
> **Ответственность**: Конвертация входных изображений в единый формат RGBA numpy-массив + извлечение/сохранение DPI metadata  
> **Соседний файл**: `image_converter.py`

---

## 1. НАЗНАЧЕНИЕ

Модуль обеспечивает единообразие обработки: любой входной файл (PNG или JPEG) конвертируется в стандартный формат — numpy RGBA-массив. Также управляет DPI metadata, критичной для print-ready output клиента (300 DPI).

---

## 2. ФУНКЦИИ

### 2.1 `load_image`

**Главная функция загрузки.**

**Вход:**
- `file_bytes`: bytes — содержимое файла (PNG или JPEG)

**Выход:** кортеж:
- `image_rgba`: numpy массив (H, W, 4), dtype uint8
- `dpi`: целое число или None (DPI из метаданных)
- `original_format`: строка `"png"` или `"jpeg"`

**Алгоритм:**
1. **Определить формат** по magic bytes:
   - PNG: первые 8 байт = `\x89PNG\r\n\x1a\n`
   - JPEG: первые 3 байта = `\xFF\xD8\xFF`
   - Иначе: выбросить ValueError с сообщением "Unsupported image format. Only PNG and JPEG are accepted."
2. **Защита от decompression bomb:** Лимит MAX_IMAGE_PIXELS = 25_000_000 ОБЯЗАН устанавливаться ВНУТРИ функции load_image() ДО каждого вызова Image.open() (не только при инициализации модуля). Глобальная настройка PIL.Image.MAX_IMAGE_PIXELS может быть сброшена другой библиотекой или тестом. Дополнительно ОБЯЗАТЕЛЬНА проверка image.size[0] * image.size[1] <= 25_000_000 ПОСЛЕ open и ДО load() как defense-in-depth. Покрывает изображения до 5000×5000 с запасом и защищает от CVE-2023-44271 (50MB PNG → десятки GB RAM).
3. **Открыть** через Pillow: `Image.open(BytesIO(file_bytes))`
4. **Eager декомпрессия:** Сразу после Image.open вызвать image.load() для принудительной декомпрессии. Это гарантирует что повреждённый файл будет обнаружен немедленно (а не при конвертации в numpy). Обернуть в try/except с понятным сообщением об ошибке.
5. **Извлечь DPI**:
   - Для PNG: `image.info.get('dpi')` — кортеж (x_dpi, y_dpi) или None
   - Для JPEG: `image.info.get('dpi')` из EXIF или Pillow metadata
   - Если DPI найден — взять первый элемент кортежа (горизонтальный DPI), округлить до целого
   - Если DPI не найден — вернуть None
6. **Конвертировать в RGBA**:
   - Если mode == 'RGBA': оставить как есть
   - Если mode == 'RGB': конвертировать в RGBA, alpha-канал = 255 (полностью непрозрачный)
   - Если mode == 'P' (palette): сначала конвертировать в RGBA
   - Если mode == 'L' (grayscale): конвертировать в RGBA
   - Любой другой mode: конвертировать в RGBA через промежуточный RGB
7. **Конвертировать в numpy**: `np.array(image_rgba, dtype=np.uint8)`
8. **Освободить промежуточные буферы:** Немедленно после np.array() вызвать image.close() и del buffer (BytesIO). Без этого: compressed bytes + BytesIO + Pillow buffer + numpy = ~192MB на один 4000×4000 файл вместо ~64MB. При последовательной обработке 20 файлов — это critical path
9. **Вернуть** кортеж (numpy_array, dpi, format_string)

---

### 2.2 `save_image_png`

**Сохранение numpy-массива в PNG-байты с сохранением DPI.**

**Вход:**
- `image_rgba`: numpy массив (H, W, 4), dtype uint8
- `dpi`: целое число или None

**Выход:** bytes — содержимое PNG-файла

**Алгоритм:**
1. Создать Pillow Image из numpy-массива: `Image.fromarray(image_rgba, mode='RGBA')`
2. Создать BytesIO буфер
3. Если dpi не None: сохранить с параметром `dpi=(dpi, dpi)`
4. Сохранить как PNG: `image.save(buffer, format='PNG', compress_level=3)`
   - `compress_level=3` — компромисс скорость/размер (compress_level=1 на 4000×4000 RGBA → ~40MB, compress_level=3 → ~20MB, compress_level=6 → ~15MB). При 20 файлов × 3 вариации: экономия ~1.2GB диска. Для preview допустим compress_level=1
5. Вернуть `buffer.getvalue()`

---

### 2.3 `create_preview`

**Создание уменьшенной копии для превью.**

**Вход:**
- `image_rgba`: numpy массив (H, W, 4), dtype uint8
- `max_size`: целое число (максимальный размер по длинной стороне, по умолчанию 800)

**Выход:** numpy массив (H', W', 4), dtype uint8 — уменьшенное изображение

**Алгоритм:**
1. Определить текущие размеры: H, W
2. Если max(H, W) <= max_size: вернуть копию оригинала (уменьшение не нужно)
3. Рассчитать коэффициент масштабирования: `scale = max_size / max(H, W)`
4. Новые размеры: `new_W = int(W * scale)`, `new_H = int(H * scale)`
5. Создать Pillow Image из numpy
6. Уменьшить через `image.resize((new_W, new_H), Image.LANCZOS)` — высококачественная интерполяция
7. Конвертировать обратно в numpy
8. **Освобождение памяти:** Немедленно вызвать del img_pil после np.array(resized). Три копии изображения (numpy original → Pillow Image → resized → numpy result) при upload 20 файлов последовательно создают давление на GC
9. Вернуть результат

**Управление памятью в save_image_png:** Немедленно вызывать del image, del buffer после getvalue(). При 20 файлах × 3 вариации — накопление невысвобожденных буферов критично

**Нюансы:**
- LANCZOS даёт лучшее качество при уменьшении (важно для preview, чтобы цвета не искажались)
- Preview используется для preview-replace — цвета должны быть репрезентативными

---

### 2.4 `detect_format`

**Определение формата по magic bytes.**

**Вход:** `file_bytes`: bytes (хотя бы первые 8 байт)

**Выход:** строка `"png"`, `"jpeg"` или None

**Алгоритм:**
1. Если длина < 3: вернуть None
2. Если `file_bytes[:8] == b'\x89PNG\r\n\x1a\n'`: вернуть `"png"`
3. Если `file_bytes[:3] == b'\xFF\xD8\xFF'`: вернуть `"jpeg"`
4. Иначе: вернуть None

---

## 3. ГРАНИЧНЫЕ СЛУЧАИ

- JPEG без EXIF/DPI metadata: dpi = None — клиент предупреждается, но обработка продолжается
- PNG с palette mode (8-bit indexed): конвертируется в RGBA через Pillow
- Grayscale JPEG: конвертируется в RGBA (серый → RGB с равными каналами → RGBA)
- Битый файл: Pillow выбросит исключение → перехватывается на уровне service, возвращается HTTP 400
- Очень маленькое изображение (меньше max_size): create_preview возвращает копию без изменений

---

## 4. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Загрузка PNG RGBA: возвращает корректный массив, DPI=300
2. Загрузка JPEG RGB: конвертация в RGBA, alpha=255, DPI из EXIF
3. Загрузка JPEG без DPI: dpi=None
4. Невалидный файл (не изображение): ValueError
5. Preview создание: 4000x3000 → 800x600 при max_size=800
6. Preview маленького: 400x300 → 400x300 (без изменений)
7. Сохранение PNG с DPI=300: выходной файл содержит DPI metadata (проверить через Pillow)
