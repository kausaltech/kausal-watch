from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction

from actions.models.plan import Plan
from orgs.models import Organization


class Command(BaseCommand):
    help = "Delete plans and related data"

    def add_arguments(self, parser):
        parser.add_argument(
            '--exclude',
            metavar='IDENTIFIER',
            action='append',
            help="Exclude the plan with the specified identifier from deletion",
        )
        parser.add_argument(
            '--no-confirm',
            action='store_true',
            help="Do not ask for confirmation but delete right away",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.DEPLOYMENT_TYPE != 'production':
            raise CommandError(
                "Sorry, for preventing accidents, this management command only works if DEBUG is true and "
                "DEPLOYMENT_TYPE is 'production'."
            )
        all_identifiers = Plan.objects.values_list('identifier', flat=True)
        if not options.get('exclude'):
            options['exclude'] = []
        for identifier in options['exclude']:
            if identifier not in all_identifiers:
                raise CommandError(f"No plan with identifier '{identifier}' exists.")
        plans_to_delete = Plan.objects.exclude(identifier__in=options['exclude'])
        plans_to_keep = Plan.objects.exclude(id__in=plans_to_delete)
        delete_identifiers = plans_to_delete.values_list('identifier', flat=True)
        orgs_to_keep = Organization.objects.available_for_plans(plans_to_keep)
        orgs_to_delete = Organization.objects.exclude(id__in=orgs_to_keep)
        num_delete_suborgs = {}
        for org in orgs_to_delete.filter(depth=1):
            # Unnecessarily inefficient, but what the hell...
            num_delete_suborgs[org] = orgs_to_delete.filter(id__in=org.get_descendants()).count()
        if options['exclude']:
            self.stdout.write(f"The following plans will not be deleted: {', '.join(options['exclude'])}")
        if delete_identifiers:
            self.stdout.write(f"The following plans will be deleted with all related data: {', '.join(delete_identifiers)}")
        if num_delete_suborgs:
            strings = []
            for org, n in num_delete_suborgs.items():
                string = org.name
                if n == 1:
                    string += f' (and 1 suborganization)'
                elif n > 1:
                    string += f' (and {n} suborganizations)'
                strings.append(string)
            self.stdout.write(f"The following organizations will be deleted: {', '.join(strings)}")
        if not options['no_confirm']:
            confirmation = input("Do you want to proceed? [y/N] ").lower()
            if confirmation != 'y':
                self.stdout.write(self.style.WARNING("Aborted by user."))
                return
        self.delete_data(plans_to_delete, orgs_to_delete)

    @transaction.atomic
    def delete_data(self, plans_to_delete, orgs_to_delete):
        _, by_type = plans_to_delete.delete()
        for model_name, n in by_type.items():
            self.stdout.write(f"Deleted {n} instances of {model_name}.")
        num_orgs = orgs_to_delete.count()
        orgs_to_delete.delete()
        # Treebeard won't tell us the deleted numbers -_-
        self.stdout.write(f"Deleted {num_orgs} organizations; information on deleted related rows not available.")
