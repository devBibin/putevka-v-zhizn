# Локальный запуск проекта

## Вариант без Docker

Этот вариант запускает только Django-сайт. Фоновые процессы из `entrypoint.sh`
при таком запуске не стартуют.

1. Откройте PowerShell в корне проекта.

2. Проверьте, что виртуальное окружение существует:

```powershell
Test-Path .\.venv\Scripts\python.exe
```

Если команда вернула `True`, можно запускать проект.

3. При необходимости установите зависимости:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. Проверьте настройки Django:

```powershell
.\.venv\Scripts\python.exe manage.py check
```

5. Примените миграции к локальной SQLite-базе:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

6. Запустите сервер:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

7. Откройте сайт:

```text
http://127.0.0.1:8000
```

По умолчанию, если переменная `DATABASE_URL` не задана, проект использует файл
`db.sqlite3` в корне репозитория.

## Вариант через Docker

Docker Compose поднимает PostgreSQL и web-контейнер:

```powershell
docker compose up -d --build
```

После запуска сайт должен быть доступен по адресу:

```text
http://127.0.0.1:8000
```

Важно: сейчас переменная `RUN_BACKGROUND_WORKERS` передается в контейнер через
`docker-compose.yml`, но `entrypoint.sh` ее не проверяет. Поэтому при Docker-
запуске фоновые процессы стартуют всегда:

- `Shadows/notification_worker.py`
- `telegram_bot_polling.py`
- `Shadows/gpt_reviewer.py`
- `Shadows/gpt_transcriber.py`
- `Shadows/gpt_transcriber_video.py`
- `Shadows/gpt_fill_form.py`

Если нужен локальный запуск только сайта, используйте вариант без Docker.
