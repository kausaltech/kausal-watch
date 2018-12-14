FROM ubuntu:18.04

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV STATIC_ROOT /srv/static
ENV MEDIA_ROOT /srv/media

RUN mkdir /code
RUN mkdir -p /srv/media

RUN apt-get update && apt-get install -y python3.7 python3-pip \
	postgresql-client-common postgresql-client gettext \
	libpq-dev
RUN apt-get install -y git-core
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN ln -s /usr/bin/pip3 /usr/bin/pip
RUN pip install --upgrade pip
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
