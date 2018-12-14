FROM python:3.7

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV STATIC_ROOT /srv/static
ENV MEDIA_ROOT /srv/media

RUN mkdir /code
RUN mkdir -p /srv/media

RUN pip install --upgrade pip
RUN apt-get update && apt-get install -y postgresql-client-common

COPY requirements.txt /code/
RUN pip install -r /code/requirements.txt
RUN pip install gunicorn

COPY . /code/
WORKDIR /code
RUN rm -f local_settings.py
RUN ./manage.py collectstatic --no-input
RUN ./manage.py compilemessages
COPY ./docker/app/docker-entrypoint.sh /

ENTRYPOINT ["/bin/bash", "/docker-entrypoint.sh"]
