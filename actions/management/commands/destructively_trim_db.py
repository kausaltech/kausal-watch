from __future__ import annotations

from django.conf import settings
from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import transaction
from reversion.models import Revision as ReversionRevision
from wagtail.models import ModelLogEntry, PageLogEntry, Revision as WagtailRevision

from actions.models.plan import Plan
from admin_site.models import Client
from orgs.models import Organization
from users.models import User
from request_log.models import LoggedRequest


class Command(BaseCommand):
    help = "Delete plans and related data"

    def add_arguments(self, parser):
        parser.add_argument(
            '--exclude-plan',
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
                "DEPLOYMENT_TYPE is 'production'.",
            )
        all_identifiers = Plan.objects.values_list('identifier', flat=True)
        if not options.get('exclude_plan'):
            options['exclude_plan'] = []
        for identifier in options['exclude_plan']:
            if identifier not in all_identifiers:
                raise CommandError(f"No plan with identifier '{identifier}' exists.")
        plans_to_delete = Plan.objects.qs.exclude(identifier__in=options['exclude_plan'])
        plans_to_keep = Plan.objects.qs.exclude(id__in=plans_to_delete)
        delete_identifiers = plans_to_delete.values_list('identifier', flat=True)
        orgs_to_keep = Organization.objects.qs.available_for_plans(plans_to_keep)
        orgs_to_delete = Organization.objects.qs.exclude(id__in=orgs_to_keep)
        num_delete_suborgs = {}
        for org in orgs_to_delete.filter(depth=1):
            # Unnecessarily inefficient, but what the hell...
            num_delete_suborgs[org] = orgs_to_delete.filter(id__in=org.get_descendants()).count()
        if options['exclude_plan']:
            self.stdout.write(f"The following plans will not be deleted: {', '.join(options['exclude_plan'])}")
        if delete_identifiers:
            self.stdout.write(f"The following plans will be deleted with all related data: {', '.join(delete_identifiers)}")
        if num_delete_suborgs:
            strings = []
            for org, n in num_delete_suborgs.items():
                string = org.name
                if n == 1:
                    string += ' (and 1 suborganization)'
                elif n > 1:
                    string += f' (and {n} suborganizations)'
                strings.append(string)
            self.stdout.write(f"The following organizations will be deleted: {', '.join(strings)}")
        self.stdout.write("Moreover, the following data will be deleted:")
        self.stdout.write("- all User instances that don't have a corresponding Person anymore")
        self.stdout.write("- all Client instances that don't have a corresponding Plan anymore")
        self.stdout.write("- all Reversion Revision instances that don't have a corresponding User anymore")
        self.stdout.write("- all Wagtail Revision instances that don't have a corresponding User anymore")
        self.stdout.write("- all Wagtail ModelLogEntry instances that don't have a corresponding User anymore")
        self.stdout.write("- all logged requests")
        if not options['no_confirm']:
            confirmation = input("Do you want to proceed? [y/N] ").lower()
            if confirmation != 'y':
                self.stdout.write(self.style.WARNING("Aborted by user."))
                return
        self.delete_data(plans_to_delete, orgs_to_delete)

    @transaction.atomic
    def delete_data(self, plans_to_delete, orgs_to_delete):
        # Delete plans
        _, by_type = plans_to_delete.delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete organizations
        num_orgs = orgs_to_delete.count()
        orgs_to_delete.delete()
        # Treebeard won't tell us the deleted numbers -_-
        self.stdout.write(f"Deleted {num_orgs} organizations; information on deleted related rows not available.")
        # Delete users without persons
        _, by_type = User.objects.filter(person__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete clients without plans
        _, by_type = Client.objects.filter(plans__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Reversion revisions without users
        _, by_type = ReversionRevision.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Wagtail revisions without users
        _, by_type = WagtailRevision.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Wagtail model log entries without users
        _, by_type = ModelLogEntry.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete Wagtail page log entries without users
        _, by_type = PageLogEntry.objects.filter(user__isnull=True).delete()
        self.print_deleted_instances_by_model(by_type)
        # Delete all logged requests
        _, by_type = LoggedRequest.objects.all().delete()
        self.print_deleted_instances_by_model(by_type)

    def print_deleted_instances_by_model(self, by_type):
        for model_name, n in by_type.items():
            self.stdout.write(f"Deleted {n} instances of {model_name}.")
