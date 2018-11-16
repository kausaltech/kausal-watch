#!/bin/bash

set -e

cd /code
python manage.py migrate --no-input
exec gunicorn --bind :8000 aplans.wsgi:application
