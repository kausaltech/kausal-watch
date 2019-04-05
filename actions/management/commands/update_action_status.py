from django.core.management.base import BaseCommand
from actions.models import Action


class Command(BaseCommand):
    help = 'Recalculates statuses and completions for all actions'

    def handle(self, *args, **options):
        for action in Action.objects.all():
            action.recalculate_status()
