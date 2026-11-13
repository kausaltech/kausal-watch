from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

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
            '--dest-name-translation',
            action='append',
            default=[],
            metavar='LANGUAGE=NAME',
            help=(
                "Translate the copy's name into LANGUAGE; may be repeated. Without any, the copy's name has no "
                'translations if --dest-name is given, and default ones otherwise.'
            ),
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
            help="Set the version name of the plan copy (default: keep the original's)",
        )
        parser.add_argument(
            '--version-name-translation',
            action='append',
            default=[],
            metavar='LANGUAGE=NAME',
            help='Translate the version name of the plan copy into LANGUAGE; may be repeated. Requires --version-name.',
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
        name_translations = _parse_translations(options['dest_name_translation'], '--dest-name-translation')
        version_name_translations = _parse_translations(options['version_name_translation'], '--version-name-translation')
        if version_name_translations and options['version_name'] is None:
            raise CommandError('--version-name-translation requires --version-name')
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
            new_plan_name_translations=name_translations,
            version_name_translations=version_name_translations,
        )


def _parse_translations(values: list[str], option: str) -> dict[str, str] | None:
    """Turn the `LANGUAGE=NAME` values of a repeatable option into a dict, or None if it was not given."""
    if not values:
        return None
    translations: dict[str, str] = {}
    for value in values:
        language, separator, text = value.partition('=')
        if not separator or not language:
            raise CommandError(f'{option} expects LANGUAGE=NAME, got {value!r}')
        translations[language] = text
    return translations
