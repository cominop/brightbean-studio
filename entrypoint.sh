#!/bin/bash
set -e
export DJANGO_SETTINGS_MODULE=config.settings.production

# Ensure media files are on the persistent volume (force re-seed)
export MEDIA_ROOT=/data/media
echo "Re-seeding media volume..."
mkdir -p /data/media
if [ -d /app/media ] && ls /app/media/* >/dev/null 2>&1; then
    rm -f /data/media/.initialized
    cp -r /app/media/* /data/media/
    echo "Media files copied from /app/media."
else
    echo "No media in image — volume starts empty."
fi
touch /data/media/.initialized

echo "Running migrations..."
python manage.py migrate --noinput
echo "Setting up superuser..."
set +e
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
# Always reset admin password on deploy
admin = User.objects.get(email='admin@brightbean.local')
admin.set_password('admin123')
admin.is_superuser = True
admin.is_staff = True
admin.save()
print('Admin password reset to admin123')
# Also ensure Jordan is active
try:
    jordan = User.objects.get(email='marketing@sharehaus.internal')
    jordan.set_password('ShareHaus2026!')
    jordan.save()
    print('Jordan password reset')
except User.DoesNotExist:
    pass
"
echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 2