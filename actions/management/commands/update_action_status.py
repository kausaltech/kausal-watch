from django.core.management.base import BaseCommand
from actions.models import Action


class Command(BaseCommand):
    help = 'Recalculates statuses and completions for all actions'

    def handle(self, *args, **options):
        for action in Action.objects.all():
            old_status = action.status
            action.recalculate_status()
            new_status = action.status
            if old_status != new_status:
                print("%s:\n\t%s -> %s" % (action, old_status, new_status))
