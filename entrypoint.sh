#!/bin/sh

echo "Waiting for PostgreSQL..."
until pg_isready -h db -U vukish; do sleep 0.1; done
echo "PostgreSQL started."

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
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'adminpass')
" | python manage.py shell

# Start Gunicorn server
#exec gunicorn Putevka.wsgi:application --bind 0.0.0.0:8000
exec python manage.py runserver 0.0.0.0:8000
