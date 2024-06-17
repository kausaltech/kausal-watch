from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import translation
from logging import getLogger

from actions.models import Plan
from notifications.notifications import NotificationType
from .send_plan_notifications import NotificationEngine

logger = getLogger(__name__)


class Command(BaseCommand):
    help = 'Sends daily notifications for all plans for which it is time to do so'

    def add_arguments(self, parser):
        # FIXME: This duplicates arguments from the management command send_plan_notifications
        type_choices = [x.identifier for x in NotificationType]
        parser.add_argument('--force-to', type=str, help='Rewrite the To field and send all emails to this address')
        parser.add_argument('--limit', type=int, help='Do not send more than this many emails')
        parser.add_argument('--only-type', type=str, choices=type_choices, help='Send only notifications of this type')
        parser.add_argument('--only-email', type=str, help='Send only the notifications that go to this email')
        parser.add_argument('--noop', action='store_true', help='Do not actually send the emails')
        parser.add_argument(
            '--dump', metavar='FILE', type=str, help='Dump generated MJML and HTML files'
        )
        parser.add_argument('--time', type=datetime.fromisoformat, help='Override current time (ISO format)')

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
