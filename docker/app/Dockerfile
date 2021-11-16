FROM ubuntu:21.10

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV STATIC_ROOT /srv/static
ENV MEDIA_ROOT /srv/media
ENV DEBIAN_FRONTEND="noninteractive" TZ="Europe/Helsinki"

RUN mkdir /code
RUN mkdir -p /srv/media

RUN apt-get update

RUN apt-get install -y python3.9 python3-pip libpython3.9-dev \
	postgresql-client-common postgresql-client libpq-dev \
	gettext git \
	zlib1g-dev libjpeg8-dev libtiff-dev libopenjp2-7-dev libwebp-dev \
    nodejs npm

RUN apt-get install -y voikko-fi libvoikko1 libhfstospell11

RUN ln -fs /usr/bin/python3.9 /usr/bin/python3
RUN ln -fs /usr/bin/python3 /usr/bin/python
RUN ln -fs /usr/bin/pip3 /usr/bin/pip
RUN pip install --upgrade pip
COPY requirements.txt requirements-prod.txt /code/
RUN pip install -r /code/requirements-prod.txt -r /code/requirements.txt

# Install ipython for convenience
RUN pip install ipython

COPY package.json package-lock.json /code/
WORKDIR /code
RUN npm install

ARG EXTRA_PYPI_INDEX
ENV EXTRA_PYPI_INDEX $EXTRA_PYPI_INDEX
ARG EXTRA_INSTALLED_APPS_VERSIONS
ENV EXTRA_INSTALLED_APPS_VERSIONS $EXTRA_INSTALLED_APPS_VERSIONS

# Install extra dependencies
RUN if [ ! -z "$EXTRA_INSTALLED_APPS_VERSIONS" ] ; then pip install --extra-index-url "${EXTRA_PYPI_INDEX}" $EXTRA_INSTALLED_APPS_VERSIONS ; fi

COPY . /code/
RUN ./manage.py collectstatic --no-input
RUN ./manage.py compilemessages
COPY ./docker/app/docker-entrypoint.sh /
COPY ./docker/app/wait-for-it.sh /

ENTRYPOINT ["/bin/bash", "/docker-entrypoint.sh"]
