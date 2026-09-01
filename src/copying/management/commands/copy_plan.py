from __future__ import annotations

from django.core.management.base import BaseCommand

from actions.models.plan import Plan

from ...main import copy_plan


class Command(BaseCommand):
    help = 'Copy a plan'

    def add_arguments(self, parser):
        parser.add_argument(
            'identifier',
            help='Copy the plan with the given identifier',
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
            help='Append the given suffix to the names of copies for models other than Plan (default: no suffix)',
        )
        parser.add_argument(
            '--root-page-title-suffix',
            help='Append the given suffix to the title of the plan root page and its translations (default: no suffix)',
        )
        parser.add_argument(
            '--version-name',
            help='Set the version name of the plan copy',
        )
        parser.add_argument(
            '--supersede-original-plan',
            help='Supersede original plan by its copy',
            action='store_true',
        )
        parser.add_argument(
            '--supersede-original-actions',
            help='Supersede original actions by their copies',
            action='store_true',
        )
        parser.add_argument(
            '--copy-indicators',
            help="Copy the plan's indicators instead of referencing the same existing indicators in both plans.",
            action='store_true',
        )

    def handle(self, *args, **options):
        plan = Plan.objects.get(identifier=options['identifier'])
        copy_plan(
            plan=plan,
            new_plan_identifier=options['dest_identifier'],
            new_plan_name=options['dest_name'],
            general_name_suffix=options['name_suffix'],
            root_page_title_suffix=options['root_page_title_suffix'],
            version_name=options['version_name'],
            supersede_original_plan=options['supersede_original_plan'],
            supersede_original_actions=options['supersede_original_actions'],
            copy_indicators=options['copy_indicators'],
        )
