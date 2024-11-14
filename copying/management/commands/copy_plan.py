from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from ...main import copy_plan
from actions.models.plan import Plan


class Command(BaseCommand):
    help = "Copy a plan"

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            help="Copy the plan with the given identifier",
        )
        parser.add_argument(
            'hostname',
            help="Choose a hostname for the new plan's site",
        )
        parser.add_argument(
            '--dest-identifier',
            help="Use the given value as the copy's identifier (default: Append '-copy')",
        )
        parser.add_argument(
            '--dest-name',
            help="Use the given value as the copy's name (default: Append a string containing the current date)",
        )
        parser.add_argument(
            '--name-suffix',
            help="Append the given suffix to the names of copies for models other than Plan (default: no suffix)",
        )
        parser.add_argument(
            '--root-page-slug-suffix',
            help="Append the given suffix (preceded by a hyphen) to the slug of the plan root page and its "
                "translations (default: 'copy')",
        )
        parser.add_argument(
            '--root-page-title-suffix',
            help="Append the given suffix to the title of the plan root page and its translations (default: no suffix)",
        )

    def handle(self, *args, **options):
        plan = Plan.objects.get(identifier=options['identifier'])
        with transaction.atomic():
            copy_plan(
                plan=plan,
                new_site_hostname=options['hostname'],
                new_plan_identifier=options['dest_identifier'],
                new_plan_name=options['dest_name'],
                general_name_suffix=options['name_suffix'],
                root_page_slug_suffix=options['root_page_slug_suffix'],
                root_page_title_suffix=options['root_page_title_suffix'],
            )
