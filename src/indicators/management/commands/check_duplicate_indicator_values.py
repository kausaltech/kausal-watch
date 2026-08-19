from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand
from django.db.models import Count

from indicators.models import Indicator, IndicatorValue

if TYPE_CHECKING:
    from indicators.models import DimensionCategory


class Command(BaseCommand):
    """
    Report indicator values that share a date and a set of dimension categories.

    Nothing in the database forbids such duplicates, but they make the values editor
    show only one of the colliding values, and the public API returns the series more
    than once. See indicators/api.py: saving the values of an affected indicator through
    the editor prunes the extra rows.
    """

    help = 'Report indicator values that duplicate another value of the same indicator'

    def add_arguments(self, parser):
        parser.add_argument('--plan', help='Only check indicators of the plan with this identifier')

    def handle(self, *args, **options):
        indicators = Indicator.objects.all()
        plan_identifier = options.get('plan')
        if plan_identifier:
            indicators = indicators.filter(plans__identifier=plan_identifier)

        # Only indicators with more than one value on some date can have duplicates.
        candidate_ids = (
            IndicatorValue.objects
            .filter(indicator__in=indicators)
            .values('indicator_id', 'date')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
            .values_list('indicator_id', flat=True)
        )
        indicators = Indicator.objects.filter(pk__in=set(candidate_ids)).prefetch_related('plans').order_by('pk')

        found = 0
        for indicator in indicators:
            duplicates = self.find_duplicates(indicator)
            if not duplicates:
                continue
            found += len(duplicates)
            plans = ', '.join(indicator.plans.values_list('identifier', flat=True))
            self.stdout.write(self.style.WARNING(f'\nindicator {indicator.pk}: {indicator.name!r} [{plans}]'))
            for (value_date, category_pks), pks in duplicates.items():
                categories = ', '.join(str(pk) for pk in category_pks) or 'none'
                self.stdout.write(f'  {value_date.isoformat()} categories=[{categories}]: values {pks}')

        if not found:
            self.stdout.write(self.style.SUCCESS('No duplicate indicator values found.'))
            return
        self.stdout.write(
            self.style.WARNING(f'\n{found} duplicated (date, categories) group(s) found.'),
        )

    def find_duplicates(self, indicator: Indicator) -> dict[tuple, list[int]]:
        """Group the indicator's values by (date, category set) and return the colliding groups."""
        groups: dict[tuple, list[int]] = defaultdict(list)
        for value in indicator.values.prefetch_related('categories').order_by('pk'):
            categories: list[DimensionCategory] = list(value.categories.all())
            groups[(value.date, tuple(sorted(c.pk for c in categories)))].append(value.pk)
        return {key: pks for key, pks in groups.items() if len(pks) > 1}
