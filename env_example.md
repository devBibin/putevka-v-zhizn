# Django Admin

DJANGO_SUPERUSER_USERNAME= # Django superuser login
DJANGO_SUPERUSER_EMAIL=    # Django superuser email
DJANGO_SUPERUSER_PASSWORD= # Django superuser password


# PostgreSQL

POSTGRES_DB=       # Database name
POSTGRES_USER=     # Database user
POSTGRES_PASSWORD= # Database password


# Telegram Bots

TG_TOKEN_ADMIN= # Telegram bot token for staff
TG_TOKEN_USERS= # Telegram bot token for users
TELEGRAM_STAFF_CHAT_IDS='{"developer": 000000000}' # JSON with staff chat ids
TELEGRAM_LOG_CHAT_ID= # Telegram chat id for logs
TG_BOT_USERS_USERNAME= # Telegram username for the users bot
TELEGRAM_SOCKS5_PROXY= # Optional SOCKS5 proxy for Telegram Bot API, examples: socks5h://user:pass@host:1080 or socks5:host:port:pass


# Common Settings

BASE_URL= # Base app URL, for example https://example.com


# GPT

GPT_TOKEN= # API token for OpenAI integration
OPENAI_PROXY= # Optional proxy for OpenAI API, example: http://user:pass@host:port or socks5://user:pass@host:1080


# ZVONOK

PUBLIC_KEY_CALL=         # Public API key
CAMPAIGN_ID=             # Campaign id
ZVONOK_API_INITIATE_URL= # Call initiation URL
ZVONOK_API_POLLING_URL=  # Call status URL


# Yandex Disk for video business cards

YANDEX_DISK_OAUTH_TOKEN=               # OAuth token for Yandex Disk
YANDEX_DISK_VIDEO_FOLDER=              # Base folder, for example Putevka/VideoBusinessCards
YANDEX_DISK_TIMEOUT_SECONDS=60         # API metadata timeout
YANDEX_DISK_UPLOAD_TIMEOUT_SECONDS=900 # Large upload timeout
