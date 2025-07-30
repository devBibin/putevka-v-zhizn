#!/bin/sh

echo "Waiting for PostgreSQL..."
until pg_isready -h db -U "$POSTGRES_USER"; do sleep 0.1; done
echo "PostgreSQL started."

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

echo "Waiting for Ngrok tunnel to be established..."

MAX_RETRIES=20
RETRY_INTERVAL=3
CURRENT_RETRIES=0

NGROK_URL=""

while [ "$CURRENT_RETRIES" -lt "$MAX_RETRIES" ]; do
    NGROK_URL=$(curl -s http://ngrok:4040/api/tunnels | grep -o '"public_url":"https:[^\"]*"' | head -1 | sed 's/"public_url":"//;s/"//')

    if [ -n "$NGROK_URL" ]; then
        echo "Ngrok URL obtained: $NGROK_URL"
        break
    fi

    echo "Ngrok URL not yet available, retrying in $RETRY_INTERVAL seconds... (Attempt $((CURRENT_RETRIES + 1))/$MAX_RETRIES)"
    sleep "$RETRY_INTERVAL"
    CURRENT_RETRIES=$((CURRENT_RETRIES + 1))
done

if [ -z "$NGROK_URL" ]; then
    echo "Failed to get Ngrok URL after multiple retries. Check ngrok logs."
fi

echo "Your public Ngrok URL: $NGROK_URL"

export NGROK_PUBLIC_URL="$NGROK_URL"

echo "Attempting to set Telegram webhook..."

python manage.py manage_telegram_webhook set --url="${NGROK_URL}" --token="${TG_TOKEN_USERS}"

if [ $? -eq 0 ]; then
    echo "Telegram webhook set successfully!"
else
    echo "Failed to set Telegram webhook. Check logs above."
fi

echo "Setup complete. Your bot should now be active at $NGROK_URL/telegram/webhook/${TG_TOKEN_USERS}/"

# Start Gunicorn server
#exec gunicorn Putevka.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
