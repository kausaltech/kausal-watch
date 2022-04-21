from celery import shared_task
from django.core import management


@shared_task
def update_index():
    management.call_command('update_index')
