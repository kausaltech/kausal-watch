#!/bin/bash

set -e
DB_CONTAINER=${1:-db}

/wait-for-it.sh ${DB_CONTAINER}:5432

cd /code
python manage.py migrate --no-input
# Log to stdout
exec uwsgi --http-socket :8000 --socket :8001 --processes 4 \
    --enable-threads \
    --ignore-sigpipe --ignore-write-errors --disable-write-exception \
    --buffer-size=32768 \
    --static-map /static=/srv/static \
    --static-map /media=/srv/media \
    --module aplans.wsgi
