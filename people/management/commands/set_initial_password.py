import secrets
import string
from django.core.management.base import BaseCommand
from django.db import transaction
from typing import List

from people.models import Person


class Command(BaseCommand):
    help = "Set password for given users if they have not logged in yet"

    def add_arguments(self, parser):
        parser.add_argument(
            'emails',
            metavar='EMAIL',
            type=str,
            nargs='+',
            help="Set password for the user with the given email, unless they logged in already",
        )
        parser.add_argument(
            '--no-initials',
            action='store_true',
            help="Do not insert the initials (first letter of first name, first letter of last name) in lower case, "
            "followed by an underscore, before the main part",
        )
        parser.add_argument(
            '--main-part',
            type=str,
            help="Main part of the password; will be randomly generated if omitted",
        )
        parser.add_argument(
            '-n',
            type=int,
            default=8,
            help="Length of the main part of the password, if it is generated randomly (default: 8)",
        )

    def handle(self, *args, **options):
        prepend_initials = not options['no_initials']
        main_part_length = options['n']
        main_part = options.get('main_part')
        if not main_part:
            alphabet = string.ascii_letters + string.digits
            main_part = ''.join(secrets.choice(alphabet) for _ in range(main_part_length))
        self.set_passwords(options['emails'], main_part, prepend_initials)

    @transaction.atomic
    def set_passwords(self, emails: List[str], main_part: str, prepend_initials: bool = True):
        for email in emails:
            self.set_password(email, main_part, prepend_initials)

    def set_password(self, email: str, main_part: str, prepend_initials: bool = True):
        try:
            person = Person.objects.get(email__iexact=email)
        except Person.DoesNotExist:
            message = f"User does not exist: {email}"
            self.stdout.write(self.style.WARNING(message))
            return

        if person.user.last_login:
            message = f"Not setting password for {email} because they already logged in."
            self.stdout.write(self.style.WARNING(message))
            return

        if prepend_initials:
            initials = person.first_name[0].lower() + person.last_name[0].lower()
            password = f'{initials}_{main_part}'
        else:
            password = main_part
        person.user.set_password(password)
        person.user.save()
        self.stdout.write(f"Set password of {email} to {password}")
