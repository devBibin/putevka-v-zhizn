# Telegram-сервис

Telegram-трафик обрабатывает отдельный воркер. Благодаря этому Django может работать на сервере, у которого нет доступа к Telegram Bot API.

## Как это работает

1. Django сохраняет исходящие сообщения в `core.TelegramMessageTask`.
2. `telegram_service` опрашивает `POST /internal/telegram/messages/claim/`, отправляет сообщения через Telegram Bot API, затем вызывает `complete` или `fail`.
3. Пользовательский бот работает через long polling внутри `telegram_service` и пересылает входящие updates в `POST /internal/telegram/updates/`.
4. Бизнес-логика регистрации остаётся в Django, но Django больше не создаёт экземпляры `TeleBot`.

Все внутренние запросы требуют заголовок:

```text
Authorization: Bearer TELEGRAM_SERVICE_TOKEN
```

## Локальный запуск через Docker

Сначала запусти Django:

```powershell
docker compose up -d --build
```

Создай локальный env-файл из шаблона:

```powershell
Copy-Item .env.telegram.example .env.telegram.local
```

Заполни `.env.telegram.local`. Значение `TELEGRAM_SERVICE_TOKEN` должно совпадать с `TELEGRAM_SERVICE_TOKEN` в `.env` Django.

Запусти Telegram-воркер:

```powershell
docker compose -f docker-compose.telegram.yml up -d --build
```

## Запуск на отдельном сервере

На сервере, у которого есть доступ к Telegram, собери и запусти контейнер:

```powershell
docker build -f telegram_service/Dockerfile -t putevka-telegram-service .
docker run --env-file .env.telegram.local putevka-telegram-service
```

Для отдельного сервера укажи:

```dotenv
TELEGRAM_DJANGO_BASE_URL=https://your-django-host.example
TELEGRAM_SERVICE_TOKEN=тот_же_секрет_что_в_env_Django
```

Сервер Django должен разрешать Telegram-сервису обращаться к `/internal/telegram/`.

## Автодеплой через GitHub Actions

Workflow `.github/workflows/deploy-telegram-service.yml` деплоит Telegram-сервис на тот же сервер, где запускается AI-сервис.

Он использует уже существующие настройки AI-деплоя:

- `AI_DEPLOY_HOST`: хост или IP сервера.
- `AI_DEPLOY_USER`: SSH-пользователь на сервере.
- `AI_DEPLOY_SSH_KEY`: приватный SSH-ключ с доступом к серверу.
- `AI_DEPLOY_PATH`: директория AI-деплоя. Если отдельная директория Telegram-сервиса не задана, workflow использует `$AI_DEPLOY_PATH/telegram-service`.

Для Telegram-сервиса нужны отдельные настройки:

- `TELEGRAM_DEPLOY_PATH`: необязательная директория деплоя Telegram-сервиса. Можно задать как GitHub Variable или Secret.
- `TELEGRAM_DEPLOY_ENV_FILE`: Secret с полным содержимым `.env.telegram.local`.

`TELEGRAM_DEPLOY_PATH` не должен совпадать с `AI_DEPLOY_PATH`: workflow использует `rsync --delete`, поэтому Telegram-сервис должен лежать в отдельной директории. Если `TELEGRAM_DEPLOY_PATH` не задан, используется безопасный путь `$AI_DEPLOY_PATH/telegram-service`.

Минимальный пример `TELEGRAM_DEPLOY_ENV_FILE`:

```dotenv
TELEGRAM_SERVICE_TOKEN=тот_же_секрет_что_в_Django
TELEGRAM_DJANGO_BASE_URL=https://your-django-host.example
TELEGRAM_WORKER_ID=telegram-worker-prod-1
TELEGRAM_WORKER_POLLING_INTERVAL=5
TELEGRAM_WORKER_LEASE_SECONDS=120

TG_TOKEN_USERS=токен_пользовательского_бота
TG_TOKEN_ADMIN=токен_админского_бота
TG_TOKEN_MAIL=токен_бота_для_обратной_связи
TG_CHAT_ID_MAIL=чат_для_обратной_связи
LOG_LEVEL=INFO
```

Workflow запускается:

- автоматически при push в `master`, если изменились файлы Telegram-сервиса, compose-файл, workflow, `requirements.txt`, `config.py` или `TELEGRAM_SERVICE.md`;
- вручную через `workflow_dispatch` в GitHub Actions.

На сервере workflow:

1. Создаёт директорию деплоя.
2. Синхронизирует только файлы Telegram-сервиса и минимальные зависимости.
3. Записывает `.env.telegram.local` из секрета `TELEGRAM_DEPLOY_ENV_FILE`.
4. Создаёт Docker-сеть `putevka_app`, если её ещё нет.
5. Запускает:

```powershell
docker compose --env-file .env.telegram.local -f docker-compose.telegram.yml up -d --build --remove-orphans
```

Посмотреть состояние сервиса на сервере:

```powershell
docker compose --env-file .env.telegram.local -f docker-compose.telegram.yml ps
docker compose --env-file .env.telegram.local -f docker-compose.telegram.yml logs -f telegram-service
```
