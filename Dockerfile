FROM python:3.7

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN mkdir /code

RUN pip install --upgrade pip
# RUN apt-get update && apt-get install -y libxml2-dev

COPY requirements.txt /code/
RUN pip install -r /code/requirements.txt
RUN pip install gunicorn

COPY . /code/
WORKDIR /code

CMD ./manage.py collectstatic --no-input
CMD gunicorn --bind :8000 aplans.wsgi:application
