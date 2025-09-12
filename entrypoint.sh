#!/bin/sh

set -e

echo "Waiting for PostgreSQL using psycopg..."
python - <<'PY'
import os, time, sys
import urllib.parse as u
try:
    import psycopg
except Exception as e:
    print("psycopg is required:", e); sys.exit(1)

url = os.environ.get("DATABASE_URL")
if not url:
    print("DATABASE_URL is not set"); sys.exit(2)

# Добавь sslmode, если платформа требует
if "sslmode=" not in url:
    sep = "&" if "?" in url else "?"
    url = url + sep + "sslmode=require"

for i in range(60):
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                print("DB is ready"); sys.exit(0)
    except Exception as e:
        print("DB not ready:", e)
        time.sleep(1)

print("DB did not become ready in time"); sys.exit(3)
PY

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
echo "
from django.contrib.auth import get_user_model
User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '0000')

if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(username, email, password)
" | python manage.py shell

#django-admin compilemessages
#TODO: включить в проде, когда понадобится перевод на русский (очень долго грузит пакеты)

python telegram_bot_polling.py &

python Shadows/gpt_reviewer.py &

# Start Gunicorn server
#exec gunicorn Putevka.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
