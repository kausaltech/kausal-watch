from celery import shared_task
from django.core import management


@shared_task
def calculate_indicators():
    management.call_command('calculate_indicators')
