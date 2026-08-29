from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from actions.models import AttributeType, CategoryType, Plan

if TYPE_CHECKING:
    from django.db.models import Model

HELP_TEXT_PREFIX = 'help_text_'


def move_help_text(obj: Model, *, force: bool) -> bool:
    """
    Move the public help text of `obj` into its admin help text.

    The public help text is cleared, so the text is only shown to admin users
    afterwards. Translations stored by modeltrans are moved as well. An admin
    help text that already has content is left alone unless `force` is set.
    Returns whether anything changed.
    """
    if obj.admin_help_text and not force:  # type: ignore[attr-defined]
        return False

    changed = False
    if obj.help_text:  # type: ignore[attr-defined]
        obj.admin_help_text = obj.help_text  # type: ignore[attr-defined]
        obj.help_text = ''  # type: ignore[attr-defined]
        changed = True

    i18n: dict[str, Any] = dict(obj.i18n or {})  # type: ignore[attr-defined]
    for key, value in list(i18n.items()):
        if not key.startswith(HELP_TEXT_PREFIX) or not value:
            continue
        i18n[f'admin_{key}'] = value
        del i18n[key]
        changed = True
    obj.i18n = i18n  # type: ignore[attr-defined]
    return changed


class Command(BaseCommand):
    help = "Move the public help texts of a plan's fields and category types to their admin help texts"

    def add_arguments(self, parser):
        parser.add_argument('plan_identifier', help='Identifier of the plan to process')
        parser.add_argument(
            '--force',
            action='store_true',
            help='Also process objects whose admin help text already has content, overwriting it',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be changed without writing anything',
        )

    def handle(self, *args, **options):
        identifier = options['plan_identifier']
        force = options['force']
        dry_run = options['dry_run']

        plan = Plan.objects.filter(identifier=identifier).first()
        if plan is None:
            raise CommandError(f"No plan found with identifier '{identifier}'")

        update_fields = ['help_text', 'admin_help_text', 'i18n']
        with transaction.atomic():
            count = 0
            for attribute_type in AttributeType.objects.for_actions(plan):
                if not move_help_text(attribute_type, force=force):
                    continue
                count += 1
                self.stdout.write(f'Field: {attribute_type}')
                if not dry_run:
                    attribute_type.save(update_fields=update_fields)

            for category_type in CategoryType.objects.filter(plan=plan):
                if not move_help_text(category_type, force=force):
                    continue
                count += 1
                self.stdout.write(f'Category type: {category_type}')
                if not dry_run:
                    category_type.save(update_fields=update_fields, skip_page_synchronization=True)

            if dry_run:
                self.stdout.write(f'Would update {count} object(s) (dry run)')
            else:
                self.stdout.write(f'Updated {count} object(s)')
