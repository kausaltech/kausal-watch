#!/bin/bash

set -e

DB_ENDPOINT=${DB_ENDPOINT:-db:5432}

if [ "$1" = 'uwsgi' -o "$1" = 'celery' -o "$1" = 'runserver' ]; then
    /wait-for-it.sh $DB_ENDPOINT
    cd /code
    if [ "$1" = 'celery' ]; then
        # If we're in a celery container, wait for the app container
        # to start first so that migrations are run.
        if ! /wait-for-it.sh -t 5 app:8000 ; then
            echo "App container didn't start, but we don't care"
        fi
    else
        python manage.py migrate --no-input
    fi
    if [ -d '/docker-entrypoint.d' ]; then
        for scr in /docker-entrypoint.d/*.sh ; do
            echo "Running $scr"
            /bin/bash $scr
        done
    fi
fi

if [ "$1" = 'uwsgi' ]; then
    # Log to stdout
    exec uwsgi --http-socket :8000 --socket :8001 --processes 4 \
        --enable-threads \
        --ignore-sigpipe --ignore-write-errors --disable-write-exception \
        --buffer-size=32768 \
        --static-map /static=/srv/static \
        --static-map /media=/srv/media \
        --module aplans.wsgi
elif [ "$1" = 'celery' ]; then
    exec celery -A aplans "$2" -l INFO
elif [ "$1" = 'runserver' ]; then
    cd /code
    python manage.py runserver 0.0.0.0:8000
fi

exec "$@"
