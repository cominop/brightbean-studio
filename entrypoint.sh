#!/bin/bash
set -e
export DJANGO_SETTINGS_MODULE=config.settings.production

# Ensure media files are on the persistent volume (Railway)
export MEDIA_ROOT=/data/media
if [ ! -f /data/media/.initialized ]; then
    echo "First run: copying media to volume..."
    mkdir -p /data/media
    cp -r /app/media/* /data/media/
    touch /data/media/.initialized
    echo "Media files copied."
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput || true

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 2