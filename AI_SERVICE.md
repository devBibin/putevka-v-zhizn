# AI-сервис

AI-задачи выполняются асинхронно. Django хранит бизнес-данные и очередь работ в модели
`core.AiTask`, а AI-воркер запускается отдельным процессом или на отдельном сервере.
Воркер общается с Django только через внутренний HTTP API `/internal/ai/`.

## Как это работает

1. Django создает `AiTask`, когда нужно обработать мотивационное письмо, видео интервью,
   видеовизитку кандидата или транскрипт интервью.
2. AI-воркер вызывает `POST /internal/ai/tasks/claim/` и забирает одну задачу в работу.
3. Пока выполняется долгая задача, воркер отправляет heartbeat-запросы, чтобы продлить lease.
4. После обработки воркер отправляет `complete` со структурированным результатом или `fail`
   с текстом ошибки.
5. Django проверяет результат и применяет его к существующим моделям проекта.

## Локальный запуск через Docker

Сначала запусти основные сервисы Django и PostgreSQL:

```powershell
docker compose up -d --build
```

Основной `docker-compose.yml` запускает:

- `web`: Django и не-AI фоновые процессы.
- `db`: PostgreSQL.

AI-воркер запускается отдельно. Создай локальный env-файл для него:

```powershell
Copy-Item .env.ai.example .env.ai.local
```

Заполни `.env.ai.local`. Минимально нужны:

```dotenv
AI_SERVICE_TOKEN=тот_же_секрет_что_в_Django
AI_DJANGO_BASE_URL=http://web:8000
OPENAI_API_KEY=токен_OpenAI
AI_WORKER_ID=ai-worker-local-1
```

Если используешь старую переменную, вместо `OPENAI_API_KEY` можно указать:

```dotenv
GPT_TOKEN=токен_OpenAI
```

Запусти AI-воркер:

```powershell
docker compose -f docker-compose.ai.yml up -d --build
```

Оба compose-файла используют одну Docker-сеть `putevka_app`, поэтому локальный AI-воркер
должен видеть Django по адресу `http://web:8000`.

Проверить контейнеры:

```powershell
docker compose ps
docker compose -f docker-compose.ai.yml ps
```

Посмотреть логи AI-воркера:

```powershell
docker compose -f docker-compose.ai.yml logs -f ai-worker
```

Остановить только AI-воркер:

```powershell
docker compose -f docker-compose.ai.yml down
```

## Частые проблемы запуска

### `Connection refused` на `http://web:8000`

Это не ошибка Telegram-прокси. Это значит, что AI-воркер не смог подключиться к Django:

- контейнер `web` еще стартует;
- контейнер `web` упал;
- AI-воркер запущен не в сети `putevka_app`;
- указан неправильный `AI_DJANGO_BASE_URL`.

Проверь:

```powershell
docker compose ps
docker compose logs -f web
docker compose -f docker-compose.ai.yml logs -f ai-worker
```

Для локального Docker значение должно быть:

```dotenv
AI_DJANGO_BASE_URL=http://web:8000
```

Если воркер запускается не в Docker, а прямо на хосте, используй:

```dotenv
AI_DJANGO_BASE_URL=http://127.0.0.1:8000
```

### Telegram proxy не работает

Переменная для Telegram:

```dotenv
TELEGRAM_SOCKS5_PROXY=socks5h://user:password@host:1080
```

Поддерживаются также короткие форматы:

```dotenv
TELEGRAM_SOCKS5_PROXY=socks5:host:1080
TELEGRAM_SOCKS5_PROXY=socks5:host:1080:password
TELEGRAM_SOCKS5_PROXY=socks5:host:1080:user:password
```

Если в логах видно `SOCKSHTTPSConnectionPool`, значит библиотека Telegram уже пытается идти
через SOCKS-прокси. Ошибки вида `Connection refused`, `timed out` или `WinError 10013`
обычно означают, что сам прокси недоступен из контейнера/хоста, заблокирован фаерволом
или указан неверный адрес.

## Запуск на отдельном сервере

На AI-сервере собирается и запускается `ai_service/Dockerfile`. Воркеру нужны переменные:

- `AI_SERVICE_TOKEN`: тот же секрет, что и в Django.
- `AI_DJANGO_BASE_URL`: публичный или приватный URL Django, например `https://app.example.org`.
- `OPENAI_API_KEY` или `GPT_TOKEN`: OpenAI-токен, хранится на AI-сервере.
- `TELEGRAM_SOCKS5_PROXY`: опциональный SOCKS5-прокси, также используется для OpenAI HTTP-трафика.

Пример:

```powershell
docker build -f ai_service/Dockerfile -t putevka-ai-worker .
docker run --env-file .env.ai.local putevka-ai-worker
```

## Деплой через GitHub Actions

Workflow `.github/workflows/deploy-ai-service.yml` деплоит только файлы AI-сервиса на отдельный
сервер и запускает:

```powershell
docker compose --env-file .env.ai.local -f docker-compose.ai.yml up -d --build --remove-orphans
```

Нужные GitHub Variables:

- `AI_DEPLOY_HOST`: хост или IP AI-сервера.
- `AI_DEPLOY_USER`: SSH-пользователь на AI-сервере.
- `AI_DEPLOY_PATH`: директория деплоя, например `/opt/putevka-ai`.

Нужные GitHub Secrets:

- `AI_DEPLOY_SSH_KEY`: приватный SSH-ключ с доступом к серверу.
- `AI_DEPLOY_ENV_FILE`: полный текст `.env.ai.local`.

Для совместимости workflow также умеет читать `AI_DEPLOY_HOST`, `AI_DEPLOY_USER` и
`AI_DEPLOY_PATH` из Secrets, если одноименные Variables не заданы.

Workflow запускается вручную из GitHub Actions или автоматически при push в ветки, если изменились файлы AI-сервиса.

`entrypoint.sh` больше не запускает старые скрипты:

- `Shadows/gpt_reviewer.py`
- `Shadows/gpt_transcriber.py`
- `Shadows/gpt_transcriber_video.py`
- `Shadows/gpt_fill_form.py`

## Постановка старых данных в очередь

После деплоя миграций можно поставить уже существующие необработанные объекты в очередь:

```powershell
python manage.py enqueue_ai_tasks
```
