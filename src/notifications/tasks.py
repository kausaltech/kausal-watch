from django.core import management

from celery import shared_task


@shared_task
def send_daily_notifications():
    management.call_command('send_daily_notifications')
