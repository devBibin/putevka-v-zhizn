#!/bin/sh

echo "Waiting for PostgreSQL..."
until pg_isready -h db -U "$POSTGRES_USER"; do sleep 0.1; done
echo "PostgreSQL started."

# Create migrations
python manage.py makemigrations --noinput

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

#тестовые данные
#python manage.py loaddata my_study/fixtures/subjects.json
#python manage.py loaddata my_study/fixtures/schools_courses.json

# Create superuser if it doesn't exist
echo "
import os
from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '0000')

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
" | python manage.py shell

#django-admin compilemessages
#TODO: включить в проде, когда понадобится перевод на русский (очень долго грузит пакеты)

python Shadows/notification_worker.py &
python telegram_bot_polling.py &
python Shadows/gpt_reviewer.py &
python Shadows/gpt_transcriber.py &
python Shadows/gpt_transcriber_video.py &
python Shadows/gpt_fill_form.py &

# Start Gunicorn server
#exec gunicorn Putevka.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
