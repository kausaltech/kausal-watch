from django.core.management.base import BaseCommand, CommandError
from django.utils import translation

from notifications.engine import NotificationEngine
from notifications.models import NotificationType
from actions.models import Plan


class Command(BaseCommand):
    help = 'Sends notifications for a single plan'

    def add_arguments(self, parser):
        type_choices = [x.identifier for x in NotificationType]
        parser.add_argument('--plan', type=str, help='Identifier of the action plan')
        parser.add_argument('--force-to', type=str, help='Rewrite the To field and send all emails to this address')
        parser.add_argument('--limit', type=int, help='Do not send more than this many emails')
        parser.add_argument('--only-type', type=str, choices=type_choices, help='Send only notifications of this type')
        parser.add_argument('--only-email', type=str, help='Send only the notifications that go to this email')
        parser.add_argument('--ignore-actions', type=str, help='Comma-separated list of action identifiers to ignore')
        parser.add_argument(
            '--ignore-indicators', type=str, help='Comma-separated list of indicator identifiers to ignore'
        )
        parser.add_argument('--noop', action='store_true', help='Do not actually send the emails')
        parser.add_argument(
            '--dump', metavar='FILE', type=str, help='Dump generated MJML and HTML files'
        )

    def handle(self, *args, **options):
        if not options['plan']:
            raise CommandError('No plan supplied')

        plan = Plan.objects.get(identifier=options['plan'])
        translation.activate(plan.primary_language)

        ignore_actions = []
        ignore_opt = options['ignore_actions'].split(',') if options['ignore_actions'] else []
        for act_id in ignore_opt:
            act = plan.actions.filter(identifier=act_id).first()
            if act is None:
                raise CommandError('Action %s does not exist' % act_id)
            ignore_actions.append(act.identifier)

        ignore_indicators = []
        ignore_opt = options['ignore_indicators'].split(',') if options['ignore_indicators'] else []
        for indicator_id in ignore_opt:
            indicator = plan.indicators.filter(identifier=indicator_id).first()
            if indicator is None:
                raise CommandError('Indicator %s does not exist' % indicator_id)
            ignore_indicators.append(indicator.identifier)

        engine = NotificationEngine(
            plan,
            force_to=options['force_to'],
            limit=options['limit'],
            only_type=options['only_type'],
            noop=options['noop'],
            only_email=options['only_email'],
            ignore_actions=ignore_actions,
            ignore_indicators=ignore_indicators,
            dump=options['dump'],
        )
        engine.generate_notifications()
        # In contrast to the management command send_daily_notifications, this does not set
        # plan.daily_notifications_triggered_at
