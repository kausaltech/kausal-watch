from celery import shared_task
from django.core import management


@shared_task
def update_action_status():
    management.call_command('update_action_status')
