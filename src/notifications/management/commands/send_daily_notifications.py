from logging import getLogger

from django.core.management.base import BaseCommand
from django.utils import translation

from actions.models import Plan
from notifications.engine import NotificationEngine

from ._notification_args import add_notification_delivery_arguments

logger = getLogger(__name__)


class Command(BaseCommand):
    help = 'Sends daily notifications for all plans for which it is time to do so'

    def add_arguments(self, parser):
        add_notification_delivery_arguments(parser)

    def handle(self, *args, **options):
        for plan in Plan.objects.all():
            if options['time']:
                now = plan.to_local_timezone(options['time'])
            else:
                now = plan.now_in_local_timezone()
            if plan.should_trigger_daily_notifications(now):
                logger.info(f'Sending daily notifications for plan {plan}')
                with translation.override(plan.primary_language):
                    engine = NotificationEngine(
                        plan,
                        force_to=options['force_to'],
                        limit=options['limit'],
                        only_type=options['only_type'],
                        noop=options['noop'],
                        only_email=options['only_email'],
                        dump=options['dump'],
                        now=now,
                    )
                    engine.generate_notifications()
                plan.daily_notifications_triggered_at = now
                plan.save()
