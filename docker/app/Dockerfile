FROM ubuntu:18.04

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV STATIC_ROOT /srv/static
ENV MEDIA_ROOT /srv/media

RUN mkdir /code
RUN mkdir -p /srv/media

# Install PostgreSQL 11
RUN apt-get update
RUN apt-get install -y gnupg wget lsb-release
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1 apt-key add -
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -sc)-pgdg main" > /etc/apt/sources.list.d/postgres.list
RUN apt-get update
RUN apt-get install -y python3.7 python3-pip \
	postgresql-client-common postgresql-client libpq-dev \
	gettext git-core
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN ln -s /usr/bin/pip3 /usr/bin/pip
RUN pip install --upgrade pip
COPY requirements.txt /code/
RUN pip install -r /code/requirements.txt
RUN pip install uwsgi

COPY . /code/
WORKDIR /code
RUN ./manage.py collectstatic --no-input
RUN ./manage.py compilemessages
COPY ./docker/app/docker-entrypoint.sh /

ENTRYPOINT ["/bin/bash", "/docker-entrypoint.sh"]
