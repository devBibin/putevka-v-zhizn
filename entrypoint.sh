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

django-admin compilemessages

python telegram_bot_polling.py &

# Start Gunicorn server
#exec gunicorn Putevka.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
