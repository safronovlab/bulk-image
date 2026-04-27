# SPEC: app/config.py

> **Слой**: APP  
> **Зависимости**: pydantic-settings  
> **Ответственность**: Единый источник конфигурации из .env переменных окружения  
> **Соседний файл**: `config.py`

---

## 1. НАЗНАЧЕНИЕ

Pydantic Settings класс, загружающий ВСЕ конфигурационные параметры из переменных окружения (через .env файл). Единый источник истины — ни один другой модуль не читает os.environ напрямую.

---

## 2. ПАРАМЕТРЫ

| Переменная | Тип | По умолчанию | Описание |
|-----------|-----|-------------|----------|
| `AUTH_USERNAME` | str | (обязательная) | Логин для авторизации |
| `AUTH_PASSWORD` | SecretStr | (обязательная) | Пароль для авторизации. Тип SecretStr — при сериализации, логировании и repr значение маскируется автоматически. Прямое чтение через метод get_secret_value |
| `CORS_ORIGINS` | list[str] | `["http://localhost:3000"]` | Разрешённые origins для CORS. Wildcard `["*"]` запрещён при включённом allow_credentials (нарушение W3C CORS спецификации). В production обязательно задавать явный список origins через .env |
| `MAX_UPLOAD_SIZE_MB` | int | 50 | Максимальный размер одного файла в MB. Верхняя граница: <= 200 |
| `MAX_TOTAL_UPLOAD_MB` | int | 500 | Максимальный суммарный размер upload в MB. Верхняя граница: <= 2000 |
| `MAX_FILES_PER_UPLOAD` | int | 20 | Максимальное количество файлов за один upload. Верхняя граница: <= 50 |
| `FILE_TTL_HOURS` | int | 24 | Время жизни файлов в часах |
| `TOKEN_TTL_HOURS` | int | 24 | Время жизни auth-токенов в часах |
| `UPLOAD_DIR` | str | `/app/data/uploads` | Директория загрузок |
| `PREVIEW_DIR` | str | `/app/data/previews` | Директория превью |
| `RESULT_DIR` | str | `/app/data/results` | Директория результатов |
| `PRESETS_PATH` | str | `/app/data/presets.json` | Путь к файлу пресетов |
| `MAX_CONCURRENT_JOBS` | int | 5 | Максимум одновременных задач на сессию |
| `CLEANUP_INTERVAL_HOURS` | int | 6 | Интервал TTL-чистки в часах |
| `PREVIEW_MAX_SIZE` | int | 800 | Максимальный размер preview по длинной стороне |
| `JOB_TIMEOUT_SECONDS` | int | 600 | Максимальное время выполнения одной job в секундах. При превышении — job помечается failed. Верхняя граница: <= 3600 |
| `MAX_IMAGE_PIXELS` | int | 25_000_000 | Максимальное количество пикселей в изображении (защита от decompression bomb). 25M = 5000×5000 с запасом. Верхняя граница: <= 100_000_000 |

---

## 3. КЛАСС

Один класс `Settings`, наследник `BaseSettings` из pydantic-settings.

**model_config**: 
- env_file = ".env"
- env_file_encoding = "utf-8"
- case_sensitive = False

---

## 4. ПРАВИЛА

- AUTH_USERNAME и AUTH_PASSWORD — обязательные. При отсутствии — приложение не стартует (Pydantic выбросит ValidationError)
- CORS_ORIGINS парсится из JSON-строки в .env (например `'["http://localhost:3000"]'`)
- Все пути (UPLOAD_DIR, PREVIEW_DIR, RESULT_DIR, PRESETS_PATH) допускают как абсолютные, так и относительные пути

---

## 5. БЕЗОПАСНОСТЬ

- **Минимальная сложность пароля:** AUTH_PASSWORD ОБЯЗАН проходить Pydantic field_validator с проверкой минимальной длины >= 12 символов. Однобуквенный пароль в .env НЕ ДОЛЖЕН проходить валидацию
- **Запрет шаблонных паролей:** field_validator для AUTH_PASSWORD ОБЯЗАН отклонять запуск приложения при использовании запрещённых значений: "change_me_to_strong_password", "password", "admin", "123456" и подобных. Клиент может оставить шаблонный пароль из .env.example в production
- **Защита секретов:** Файл `.env` ОБЯЗАН быть добавлен в `.gitignore`. В production использовать Docker secrets или переменные окружения без .env-файла. AUTH_PASSWORD хранится как SecretStr — при логировании и repr маскируется автоматически
- **Валидация путей при старте:** Pydantic model_validator ОБЯЗАН проверять что все *_DIR пути (UPLOAD_DIR, PREVIEW_DIR, RESULT_DIR) и PRESETS_PATH резолвятся внутрь рабочей директории приложения через Path.resolve().is_relative_to(base). Запрещены пути вида /etc, /proc и любые за пределами app root
- **Запрет CORS wildcard:** Pydantic model_validator ОБЯЗАН блокировать запуск приложения при CORS_ORIGINS=["*"]. Wildcard при allow_credentials=True нарушает W3C CORS спецификацию и открывает CSRF-вектор. В .env.example ОБЯЗАН быть указан конкретный origin (http://localhost:3000), а не wildcard
- **Верхние границы числовых параметров:** MAX_UPLOAD_SIZE_MB, MAX_TOTAL_UPLOAD_MB и MAX_FILES_PER_UPLOAD ОБЯЗАНЫ иметь Pydantic верхние границы (le=). Без ограничений злонамеренная конфигурация (MAX_UPLOAD_SIZE_MB=999999) позволяет OOM-kill контейнера

---

## 5. ТЕСТОВЫЕ СЦЕНАРИИ (для QA)

1. Все переменные заданы → Settings создаётся успешно
2. AUTH_USERNAME не задан → ValidationError при старте
3. Значения по умолчанию используются когда переменные не заданы
4. CORS_ORIGINS парсится из JSON-строки
