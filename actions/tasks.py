from celery import shared_task
from django.core import management


@shared_task
def update_action_status():
    management.call_command('update_action_status')


@shared_task
def update_index():
    # Actually this is not specific to the `actions` app, so maybe should be in a different file
    management.call_command('update_index')
