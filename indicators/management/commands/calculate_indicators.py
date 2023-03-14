from datetime import timedelta
import logging

from django.core.management.base import BaseCommand
from indicators.models import Indicator, IndicatorValue


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recalculates meta-indicator values'

    def handle_share_of_updated_indicators(self, indicator, plan):
        now = plan.now_in_local_timezone()
        all_actions = list(plan.actions.visible_for_user(None).exclude(status__is_completed=True))
        if not all_actions:
            return
        up_to_date = 0
        for action in all_actions:
            if now - action.updated_at <= timedelta(days=3 * 30):
                up_to_date += 1

        share = round(up_to_date * 100 / len(all_actions), 1)
        try:
            val = indicator.values.get(date=now.date())
        except IndicatorValue.DoesNotExist:
            val = IndicatorValue(indicator=indicator, date=now.date())
        val.value = share
        val.save()
        indicator.handle_values_update()

    def handle_average_days_since_last_update(self, indicator, plan):
        now = plan.now_in_local_timezone()
        all_actions = list(plan.actions.visible_for_user(None).exclude(status__is_completed=True))
        updated_actions = 0
        days_since_update = 0
        for action in all_actions:
            if not action.updated_at:
                continue
            updated_actions += 1
            days_since_update += (now - action.updated_at).days

        if not updated_actions:
            return

        avg = round(days_since_update / updated_actions, 1)
        try:
            val = indicator.values.get(date=now.date())
        except IndicatorValue.DoesNotExist:
            val = IndicatorValue(indicator=indicator, date=now.date())
        val.value = avg
        val.save()
        indicator.handle_values_update()

    def handle(self, *args, **options):
        IDENTIFIERS = ['share_of_updated_indicators', 'average_days_since_last_update']

        for identifier in IDENTIFIERS:
            indicators = Indicator.objects.filter(identifier=identifier)
            for ind in indicators:
                if ind.time_resolution != 'day':
                    ind.time_resolution = 'day'
                    ind.save(update_fields=['time_resolution'])
                if ind.levels.count() != 1:
                    logger.error('Indicator %s has %d active plans' % (str(ind), ind.levels.count()))
                plan = ind.plans.first()
                handler = getattr(self, 'handle_%s' % identifier)
                handler(ind, plan)
