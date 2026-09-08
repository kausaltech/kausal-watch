from django.core.management.base import BaseCommand, CommandError
from django.utils import translation

from actions.models import Plan
from notifications.engine import NotificationEngine

from ._notification_args import add_notification_delivery_arguments


def _get_ignored_identifiers(plan: Plan, option: str | None, relation_name: str, item_name: str) -> list[str]:
    ignore_opt = option.split(',') if option else []
    ignored = []
    related_objects = getattr(plan, relation_name)
    for identifier in ignore_opt:
        item = related_objects.filter(identifier=identifier).first()
        if item is None:
            raise CommandError('%s %s does not exist' % (item_name, identifier))
        ignored.append(item.identifier)
    return ignored


class Command(BaseCommand):
    help = 'Sends notifications for a single plan'

    def add_arguments(self, parser):
        parser.add_argument('--plan', type=str, help='Identifier of the action plan')
        add_notification_delivery_arguments(parser)
        parser.add_argument('--ignore-actions', type=str, help='Comma-separated list of action identifiers to ignore')
        parser.add_argument(
            '--ignore-indicators',
            type=str,
            help='Comma-separated list of indicator identifiers to ignore',
        )

    def handle(self, *args, **options):
        if not options['plan']:
            raise CommandError('No plan supplied')

        plan = Plan.objects.get(identifier=options['plan'])
        translation.activate(plan.primary_language)

        ignore_actions = _get_ignored_identifiers(plan, options['ignore_actions'], 'actions', 'Action')
        ignore_indicators = _get_ignored_identifiers(plan, options['ignore_indicators'], 'indicators', 'Indicator')

        if options['time']:
            now = plan.to_local_timezone(options['time'])
        else:
            now = plan.now_in_local_timezone()

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
            now=now,
        )
        engine.generate_notifications()
        # In contrast to the management command send_daily_notifications, this does not set
        # plan.daily_notifications_triggered_at
