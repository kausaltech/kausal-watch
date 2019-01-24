#!/bin/bash

set -e

cd /code
python manage.py migrate --no-input
# Log to stdout
exec gunicorn --access-logfile - --bind :8000 aplans.wsgi:application
