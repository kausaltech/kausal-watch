FROM ubuntu:22.04

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV STATIC_ROOT /srv/static
ENV MEDIA_ROOT /srv/media
ENV DEBIAN_FRONTEND="noninteractive" TZ="Europe/Helsinki"

RUN mkdir /code
RUN mkdir -p /srv/media

RUN apt-get update

RUN apt-get install -y python3.11 python3-pip libpython3.11-dev \
	postgresql-client-common postgresql-client libpq-dev \
	gettext git \
	zlib1g-dev libjpeg8-dev libtiff-dev libopenjp2-7-dev libwebp-dev \
    nodejs npm

RUN apt-get install -y voikko-fi libvoikko1 libhfstospell11

RUN apt-get install -y binutils libproj-dev gdal-bin

RUN ln -fs /usr/bin/python3.11 /usr/bin/python3
RUN ln -fs /usr/bin/python3 /usr/bin/python
RUN ln -fs /usr/bin/pip3 /usr/bin/pip

#RUN useradd --no-log-init -m -d /appuser -r appuser
#RUN chown appuser /code /srv/media /srv

# Switch to the app user
#USER appuser

RUN pip install --upgrade pip

ARG EXTRA_PYPI_INDEX

COPY requirements.txt requirements-prod.txt /code/
RUN pip install -r /code/requirements-prod.txt -r /code/requirements.txt

ARG INSTALL_DEV_DEPS
COPY requirements-dev.txt /code/
RUN if [ ! -z "${INSTALL_DEV_DEPS}" ] ; then pip install -r /code/requirements-dev.txt ; fi


# Install extra dependencies
COPY requirements-kausal.txt /code/
RUN \
    if [ ! -z "$EXTRA_PYPI_INDEX" ] ; then \
        pip install --extra-index-url "${EXTRA_PYPI_INDEX}" -r /code/requirements-kausal.txt ; \
    fi

# Install ipython for convenience
RUN pip install ipython

COPY package.json package-lock.json /code/
WORKDIR /code
RUN npm install

COPY . /code/

RUN ./manage.py collectstatic --no-input
RUN ./manage.py compilemessages
RUN pybabel compile -D notifications -d locale
COPY ./docker/app/docker-entrypoint.sh /
COPY ./docker/app/wait-for-it.sh /

EXPOSE 8000/tcp
ENTRYPOINT ["/bin/bash", "/docker-entrypoint.sh"]
