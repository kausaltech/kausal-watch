from django.core.management.base import BaseCommand
from people.models import Person


class Command(BaseCommand):
    help = 'Updates avatars for persons (if needed)'

    def handle(self, *args, **options):
        for person in Person.objects.all():
            if not person.should_update_avatar():
                continue
            print(person)
            person.download_avatar()
