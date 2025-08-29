
# Django Admin (суперпользователь)

DJANGO_SUPERUSER_USERNAME= # Логин суперпользователя Django  
DJANGO_SUPERUSER_EMAIL=    # Email суперпользователя Django  
DJANGO_SUPERUSER_PASSWORD= # Пароль суперпользователя Django


# PostgreSQL

POSTGRES_DB=       # Название базы данных  
POSTGRES_USER=     # Пользователь PostgreSQL  
POSTGRES_PASSWORD= # Пароль PostgreSQL


# Telegram Bots

TG_TOKEN_ADMIN= # Токен Telegram-бота для администраторов  
TG_TOKEN_USERS= # Токен Telegram-бота для пользователей  
TELEGRAM_STAFF_CHAT_IDS='{"developer": 000000000}' # JSON с ID чатов сотрудников (пример: {"admin":12345})  
TELEGRAM_LOG_CHAT_ID= # ID чата для логов  
TG_BOT_USERS_USERNAME= # @username бота для пользователей (example_bot)


# Общие настройки

BASE_URL= # Базовый URL приложения (например, https://example.com)  


# GPT

GPT_TOKEN= # API-токен для ChatGPT интеграции


# Интеграция сервиса ZVONOK

PUBLIC_KEY_CALL=         # Публичный ключ API Zvonok  
CAMPAIGN_ID=             # ID кампании обзвона  
ZVONOK_API_INITIATE_URL= # URL API для инициации звонка  
ZVONOK_API_POLLING_URL=  # URL API для проверки статуса звонка
