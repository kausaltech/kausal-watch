from django.core import management

from celery import shared_task


@shared_task
def calculate_indicators():
    management.call_command('calculate_indicators')
