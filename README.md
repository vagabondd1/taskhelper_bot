# task_helper

Telegram-бот для помощи в решении задач по программированию.

Поддерживает два режима:
- **Guided mode** — пошаговое обучение через фиксированное меню кнопок
- **Full solution mode** — полное решение задачи с объяснением

## Быстрый старт

### 1. Подготовка окружения

```bash
cp .env.example .env
```

Заполни `.env`:

```env
TELEGRAM_BOT_TOKEN=...
QWEN_API_KEY=...
POSTGRES_PASSWORD=...
```

### 2. Запуск

```bash
docker compose up --build
```

Миграции применяются автоматически при старте контейнера.

### 3. Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Postgres должен быть запущен локально, POSTGRES_HOST=localhost
alembic upgrade head
python main.py
```

## Структура проекта

```
app/
├── bot/          # Telegram handlers, keyboards, middleware
├── services/     # Бизнес-логика (use-cases)
├── llm/          # Qwen-клиент, prompt builder, шаблоны промптов
├── db/           # SQLAlchemy модели, репозитории, UnitOfWork
├── schemas/      # Pydantic схемы
└── core/         # Config, logging, utils
alembic/          # Миграции БД
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather | — |
| `QWEN_API_KEY` | API ключ Qwen | — |
| `QWEN_BASE_URL` | Base URL Qwen API | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `QWEN_MODEL` | Модель | `qwen-plus` |
| `QWEN_TIMEOUT` | Таймаут запроса к LLM (сек) | `60` |
| `GUIDED_MODE_MAX_TOKENS` | Лимит токенов в guided mode | `512` |
| `FULL_SOLUTION_MAX_TOKENS` | Лимит токенов в full solution mode | `2048` |
| `POSTGRES_HOST` | Хост Postgres | `postgres` |
| `POSTGRES_PORT` | Порт Postgres | `5432` |
| `POSTGRES_DB` | Имя БД | `task_helper` |
| `POSTGRES_USER` | Пользователь БД | `postgres` |
| `POSTGRES_PASSWORD` | Пароль БД | — |
| `LOG_LEVEL` | Уровень логов | `INFO` |
| `MAX_USER_MESSAGE_LENGTH` | Макс. длина сообщения пользователя | `4096` |
