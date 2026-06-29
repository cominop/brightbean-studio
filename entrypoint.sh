#!/bin/bash
set -e
echo "Running migrations..."
python manage.py migrate --noinput
echo "Syncing media to volume..."
mkdir -p /data/media
cp -rn /app/media/* /data/media/ || true
echo "Verify file access:"
ls -la /data/media/media_library/2026/06/img_1782623940773.jpg 2>&1 || echo "NOT FOUND"
file /data/media/media_library/2026/06/img_1782623940773.jpg 2>&1 || echo "FILE CMD FAILED"
echo "MEDIA_ROOT env: $MEDIA_ROOT"
echo "Python MEDIA_ROOT:"
python3 -c "from django.conf import settings; print(settings.MEDIA_ROOT)" 2>&1 || echo "DJANGO IMPORT FAILED"
echo "Setting up superuser..."
set +e
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@brightbean.local').exists():
    User.objects.create_superuser('admin@brightbean.local', 'BrightBean2026!')
    print('Superuser created.')
else:
    admin = User.objects.get(email='admin@brightbean.local')
    admin.set_password('BrightBean2026!')
    admin.save()
    print('Superuser password reset.')
"
echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 2