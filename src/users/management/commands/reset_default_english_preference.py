from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand, CommandError
from wagtail.users.models import UserProfile

from actions.models import Plan

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


def _is_english(language_code: str) -> bool:
    return language_code.split('-', 1)[0].lower() == 'en'


class Command(BaseCommand):
    help = (
        'Clear UserProfile.preferred_language when it is set to "en" but none of the '
        "user's adminable plans have English as their primary language. This corrects "
        'a regression from Sep 2025 (commit 7705a74) that seeded new profiles with '
        'English regardless of plan. Once cleared, AdminMiddleware re-seeds the '
        'preference to plan.primary_language on the next admin request.'
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            '--plan',
            type=str,
            help='Limit to users whose adminable plans include this plan identifier',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without saving',
        )

    def handle(self, *args, **options):
        dry_run: bool = options['dry_run']
        target_plan: Plan | None = None
        if options.get('plan'):
            try:
                target_plan = Plan.objects.get(identifier=options['plan'])
            except Plan.DoesNotExist as exc:
                raise CommandError(f'No plan with identifier {options["plan"]!r}') from exc

        profiles = UserProfile.objects.filter(preferred_language='en').select_related('user')

        checked = 0
        cleared = 0
        skipped_no_plan = 0
        skipped_english_plan = 0

        for profile in profiles.iterator():
            checked += 1
            user = profile.user
            plans = user.get_adminable_plans()
            plan_langs = list(plans.values_list('primary_language', flat=True))

            if not plan_langs:
                skipped_no_plan += 1
                continue
            if any(_is_english(lang) for lang in plan_langs):
                skipped_english_plan += 1
                continue
            if target_plan is not None and not plans.filter(pk=target_plan.pk).exists():
                continue

            self.stdout.write(
                f'{"[dry-run] " if dry_run else ""}Clearing preferred_language for '
                f'{user.email} (plan primary languages: {sorted(set(plan_langs))})'
            )
            if not dry_run:
                profile.preferred_language = ''
                profile.save(update_fields=['preferred_language'])
            cleared += 1

        verb = 'Would clear' if dry_run else 'Cleared'
        self.stdout.write(
            self.style.SUCCESS(
                f'{verb} {cleared} of {checked} UserProfiles with preferred_language="en" '
                f'(skipped {skipped_english_plan} with an English-primary plan, '
                f'{skipped_no_plan} with no adminable plan).'
            )
        )
