# TaskHelper Bot

Telegram-бот для пошагового решения задач по программированию. Работает поверх LLM (Qwen через OpenAI-совместимый API), хранит состояние в PostgreSQL и использует Redis для распределённого rate limiting и кулдауна задач.

---

## Содержание

1. [Возможности](#возможности)
2. [Архитектура](#архитектура)
3. [Структура проекта](#структура-проекта)
4. [Быстрый старт](#быстрый-старт)
5. [Переменные окружения](#переменные-окружения)
6. [Команды и кнопки](#команды-и-кнопки)
7. [Поток данных одного запроса](#поток-данных-одного-запроса)
8. [Безопасность](#безопасность)
9. [Миграции](#миграции)
10. [Эксплуатация](#эксплуатация)

---

## Возможности

- **Guided mode (шаг за шагом).** Бот строит план из 3–7 шагов и ведёт пользователя по нему: подсказки только на текущий шаг, объяснение предыдущего ответа, проверка гипотезы, перепроверка по запросу «Это неверно».
- **Full solution mode.** Полное решение с кодом и пояснением одной кнопкой.
- **Автоматическое управление шагами.** Инкремент шагов делает только серверный код, LLM не контролирует прогресс — это исключает скачки и зависание плана.
- **Защита от prompt injection.** Пользовательский ввод оборачивается в `<user_input>…</user_input>` с HTML-экранированием; системный промпт прямо запрещает следовать инструкциям внутри этих тегов.
- **Per-user rate limit и cooldown.** Sliding window через атомарный Lua-скрипт в Redis; отдельный кулдаун на отправку новой задачи.
- **Сериализация запросов одного пользователя.** `pg_advisory_xact_lock` исключает гонку при двойном клике.
- **Очистка истории.** Команда `/clear` и кнопка «Очистить чат» удаляют последние ~200 сообщений и закрывают активную сессию.

---

## Архитектура

```
┌────────────┐     update     ┌──────────────────┐
│  Telegram  │ ─────────────▶ │  aiogram router  │
└────────────┘                └────────┬─────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
   RateLimitMiddleware       DbSessionMiddleware        UserLockMiddleware
       (Redis ZSET)        (AsyncSession per update)   (pg_advisory_xact_lock)
                                       │
                                       ▼
                              ┌─────────────────┐
                              │    Handlers     │  app/bot/handlers
                              └────────┬────────┘
                                       │
                                       ▼
                       ┌──────────────────────────────┐
                       │   Services (use-cases)       │  app/services
                       │   GuidedService, TaskService │
                       └─────────┬─────────┬──────────┘
                                 │         │
                       ┌─────────▼──┐   ┌──▼─────────┐
                       │  UoW + DB  │   │ LLM client │
                       │ Postgres   │   │   Qwen     │
                       └────────────┘   └────────────┘
```

Слои изолированы: handlers ничего не знают о БД и LLM, сервисы оперируют доменными объектами через `UnitOfWork`, LLM-клиент возвращает строго типизированные Pydantic-структуры.

---

## Структура проекта

```
app/
├── bot/
│   ├── handlers/messages.py    # Обработчики сообщений и кнопок
│   ├── keyboards.py            # ReplyKeyboardMarkup для каждого режима
│   ├── middleware.py           # Rate limit, DB session, user lock
│   └── sender.py               # Безопасная отправка с разбиением на части
├── services/
│   ├── base.py                 # Общая логика: вызов LLM, сохранение state
│   ├── guided_service.py       # Guided mode: hint, next step, validate, и т.д.
│   ├── task_service.py         # Создание новой задачи + cooldown
│   └── factory.py              # Сборка сервисов
├── llm/
│   ├── adapter.py              # Интерфейс BaseLLMClient
│   ├── qwen_client.py          # Реализация поверх openai-sdk
│   ├── prompt_builder.py       # Сборка messages-массива для LLM
│   └── prompts/                # Системный промпт + шаблоны для каждого action
├── db/
│   ├── models.py               # SQLAlchemy модели: User, Session, Message, Attempt, EventLog
│   ├── repositories/           # Per-table репозитории
│   ├── uow.py                  # Unit of Work + advisory lock namespaces
│   └── engine.py               # async_session_factory
├── schemas/
│   ├── bot_response.py         # Результат сервисов → handler
│   ├── llm_response.py         # JSON-контракт ответа LLM
│   └── session_state.py        # Контекст сессии для prompt builder
└── core/
    ├── config.py               # Pydantic Settings из .env
    ├── logging.py              # structlog (JSON)
    ├── redis.py                # Redis client singleton
    └── utils.py                # sanitize_text, validate_user_input_length

alembic/versions/               # Миграции БД (4 ревизии)
docker-compose.yml              # Bot + Postgres + Redis с healthcheck
Dockerfile                      # Python 3.12-slim, non-root user
entrypoint.sh                   # alembic upgrade head && python main.py
main.py                         # Точка входа: dispatcher, polling, graceful shutdown
```

---

## Быстрый старт

### Требования

- Docker и Docker Compose
- Telegram bot token (получается у `@BotFather`)
- Доступ к Qwen API (или совместимому endpoint)

### 1. Подготовка окружения

```bash
cp .env.example .env
```

Заполни обязательные поля:

```env
TELEGRAM_BOT_TOKEN=...
QWEN_API_KEY=...
POSTGRES_PASSWORD=...
```

### 2. Запуск

```bash
docker compose up -d --build
```

Стартуют три сервиса: `bot`, `postgres`, `redis`. Контейнер бота ждёт `healthy`-статуса БД и Redis, затем `entrypoint.sh` применяет миграции и запускает polling.

### 3. Проверка

```bash
docker compose ps
docker compose logs bot --tail=20
```

В логах должны появиться `Start polling` и `Run polling for bot @<username>`.

### 4. Остановка

```bash
docker compose down
```

Данные Postgres сохраняются в named volume `postgres_data`. Redis — без персистентности (только rate limit и cooldown).

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от `@BotFather` | — |
| `QWEN_API_KEY` | API-ключ LLM-провайдера | — |
| `QWEN_BASE_URL` | Base URL OpenAI-совместимого endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `QWEN_MODEL` | Имя модели | `qwen-plus` |
| `QWEN_TIMEOUT` | Таймаут запроса к LLM, сек | `60` |
| `GUIDED_MODE_MAX_TOKENS` | Лимит токенов в guided mode | `512` |
| `FULL_SOLUTION_MAX_TOKENS` | Лимит токенов в full solution mode | `2048` |
| `POSTGRES_HOST` | Хост Postgres | `postgres` |
| `POSTGRES_PORT` | Порт Postgres | `5432` |
| `POSTGRES_DB` | Имя БД | `task_helper` |
| `POSTGRES_USER` | Пользователь БД | `postgres` |
| `POSTGRES_PASSWORD` | Пароль БД | — |
| `REDIS_URL` | URL Redis | `redis://redis:6379/0` |
| `RATE_LIMIT_REQUESTS` | Лимит запросов в окне | `20` |
| `RATE_LIMIT_WINDOW_SECONDS` | Размер окна, сек | `60` |
| `NEW_TASK_COOLDOWN_SECONDS` | Кулдаун между новыми задачами | `10` |
| `LOG_LEVEL` | DEBUG / INFO / WARNING / ERROR / CRITICAL | `INFO` |
| `MAX_USER_MESSAGE_LENGTH` | Макс. длина пользовательского ввода | `4096` |

---

## Команды и кнопки

### Команды

| Команда | Действие |
|---|---|
| `/start` | Приветствие и стартовое меню |
| `/clear` | Удаляет последние ~200 сообщений и закрывает активную сессию |

### Стартовое меню

| Кнопка | Действие |
|---|---|
| `Описать задачу` | Сбрасывает активную сессию и просит текст задачи |
| `Очистить чат` | То же, что `/clear` |
| `Завершить` | Закрывает сессию (только если есть активная) |

### Меню guided mode

| Кнопка | Действие |
|---|---|
| `Подсказка` | Минимальный намёк строго на текущий шаг |
| `Следующий шаг` | Помечает текущий шаг выполненным и анонсирует следующий по плану |
| `Проверить идею` | Запрашивает гипотезу пользователя и оценивает её |
| `Мой контекст` | Просит пользователя поделиться текущим ходом мыслей; принимается как новый прогресс без оценки |
| `Объяснить` | Раскрывает предыдущий ответ ассистента |
| `Подсказка по коду` | Короткий код-сниппет / псевдокод для текущего шага |
| `Это неверно` | Перепроверка предыдущего ответа: либо признать ошибку, либо защитить ответ |
| `Завершить` | Закрывает сессию |

После прохождения последнего шага меню сворачивается до одной кнопки `Завершить`.

---

## Поток данных одного запроса

1. Telegram присылает update в polling-цикл aiogram.
2. `RateLimitMiddleware` атомарно проверяет sliding window в Redis (Lua-скрипт). Превышение — отказ с `retry_after`.
3. `DbSessionMiddleware` создаёт `AsyncSession` на этот update.
4. `UserLockMiddleware` берёт `pg_advisory_xact_lock(namespace, user_id)` — все запросы одного пользователя сериализуются на уровне транзакции.
5. Handler сопоставляет текст с кнопкой/командой и вызывает соответствующий метод сервиса.
6. Сервис: достаёт сессию через UoW, собирает контекст (`SessionContext`), вызывает LLM с шаблоном промпта под action.
7. LLM возвращает JSON по фиксированной схеме `LLMResponse`. При невалидном JSON — fallback с понятным сообщением пользователю.
8. Сервис применяет `state_update` к сессии (task_summary, plan_steps, progress_summary, switch_mode, awaiting_hypothesis), пишет сообщение в `messages`, логирует событие в `event_logs`, коммитит транзакцию.
9. Handler рендерит `BotResponse` → выбирает клавиатуру, отправляет ответ через `sender.py` (разбиение по 4096 символов, опциональный Markdown).

---

## Безопасность

- **Prompt injection.** Любой пользовательский ввод передаётся в LLM только внутри `<user_input>…</user_input>` с предварительным HTML-экранированием `& < >`. Системный промпт явно требует игнорировать любые инструкции внутри этих тегов.
- **Topic guardrail.** На действие `new_task` системный промпт обязывает LLM проверить тематику; не-программистские запросы получают фиксированный отказ без обращения к содержимому.
- **Rate limit.** Распределённый sliding window через Redis ZSET + атомарный Lua-скрипт. Корректен при нескольких инстансах бота и переживает перезапуск.
- **Cooldown на новую задачу.** Отдельный `SET NX EX` ключ — даже при свободном rate limit-окне нельзя спамить тяжёлыми new_task-запросами.
- **Сериализация на пользователя.** `pg_advisory_xact_lock` не даёт двум обработчикам одного пользователя одновременно изменять состояние сессии.
- **Контейнер.** Запускается под non-root пользователем `appuser`, образ собран на `python:3.12-slim`.
- **Fail-open Redis.** Если Redis временно недоступен — rate limit пропускает запросы, а не блокирует всех, чтобы сбой инфраструктуры не клал бота.

---

## Миграции

Применяются автоматически при старте контейнера (`entrypoint.sh` → `alembic upgrade head`).

Создание новой ревизии локально:

```bash
docker compose exec bot alembic revision --autogenerate -m "describe change"
docker compose restart bot
```

Откат на предыдущую ревизию:

```bash
docker compose exec bot alembic downgrade -1
```

---

## Эксплуатация

### Логи

```bash
docker compose logs -f bot
```

Формат — JSON (structlog), удобно для агрегаторов. Уровень настраивается через `LOG_LEVEL`.

### Healthcheck

- `bot` — проверяет, что PID 1 это `python` (не пустой контейнер в restart-loop).
- `postgres` — `pg_isready`.
- `redis` — `redis-cli ping`.

Контейнер бота не стартует, пока БД и Redis не сообщат `healthy`.

### Перезапуск только бота

```bash
docker compose restart bot
```

### Полный пересбор (после изменения зависимостей или Dockerfile)

```bash
docker compose up -d --build bot
```

### Подключение к БД

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB
```

### Очистка Redis

```bash
docker compose exec redis redis-cli FLUSHDB
```

Сбросит rate limit и cooldown для всех пользователей.
