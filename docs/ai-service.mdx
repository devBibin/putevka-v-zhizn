---
title: "AI-сервис"
description: "Обзор отдельного worker-сервиса для AI-задач."
---

# AI-сервис

Папка `ai_service/` содержит отдельный worker-сервис для асинхронных AI-задач, которые использует Django-приложение.

## За что отвечает

- Транскрибирует аудио и видео.
- Помогает staff-процессам с проверкой материалов.
- Заполняет или нормализует данные форм через LLM-хелперы.
- Изолирует AI-зависимости и runtime от основного Django-процесса.

## Основные файлы

| Путь | Назначение |
| --- | --- |
| `ai_service/worker.py` | Entry point worker-а. |
| `ai_service/client.py` | Хелперы интеграции со стороны Django. |
| `ai_service/openai_runtime.py` | Адаптер OpenAI runtime. |
| `ai_service/tasks/` | Реализации задач транскрибации, проверки и заполнения форм. |
| `docker-compose.ai.yml` | Docker Compose-конфигурация AI-worker-а. |
| `.env.ai.example` | Пример переменных окружения для AI-сервиса. |

## Деплой

Для AI-worker-а есть отдельный GitHub Actions workflow:

```text
.github/workflows/deploy-ai-service.yml
```

Он синхронизирует файлы AI-сервиса на сервер, загружает `.env.ai.local` из secrets репозитория и запускает worker через Docker Compose.
