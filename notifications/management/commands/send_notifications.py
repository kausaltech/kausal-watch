import typing
from datetime import date, timedelta
from dataclasses import dataclass

from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import activate
from markupsafe import Markup

from actions.models import Plan, ActionTask, Action, ActionContactPerson
from people.models import Person
from notifications.models import NotificationType

from logging import getLogger


logger = getLogger(__name__)


MINIMUM_NOTIFICATION_PERIOD = 5  # days
TASK_DUE_SOON_DAYS = 30


class Notification:
    type: NotificationType
    plan: Plan
    obj: typing.Union[Action, ActionTask]

    def _get_type(self):
        return self.type.identifier

    def get_context(self):
        # Implement in subclass
        raise NotImplementedError()

    def mark_sent(self, person: Person):
        now = timezone.now()
        self.obj.sent_notifications.create(sent_at=now, person=person, type=self._get_type())

    def notification_last_sent(self, person: Person) -> typing.Optional[int]:
        last_notification = self.obj.sent_notifications.filter(
            person=person, type=self._get_type()
        ).order_by('-sent_at').first()
        if not last_notification:
            return None
        else:
            return (timezone.now() - last_notification.sent_at).days

    def _queue_notification(self, person: Person):
        person._notifications.setdefault(self._get_type(), []).append(self)


class TaskLateNotification(Notification):
    type = NotificationType.TASK_LATE

    def __init__(self, task: ActionTask, days_late: int):
        super().__init__()
        self.obj = task
        self.days_late = days_late

    def get_context(self):
        return dict(task=self.obj.get_notification_context(), days_late=self.days_late)

    def generate_notifications(self, action_contacts: typing.List[Person]):
        for person in action_contacts:
            days = self.notification_last_sent(person)
            if days is not None:
                if days < MINIMUM_NOTIFICATION_PERIOD:
                    # We don't want to remind too often
                    continue
                if self.days_late not in (1, 7) and not (self.days_late % 30 == 0):
                    # If we have reminded about this before, let's only
                    # send a reminder if it's late one day, a week or 30, 60, 90... days
                    continue
            else:
                # If we have never reminded about this, send a notification
                # no matter how many days are left.
                pass

            self._queue_notification(person)


class TaskDueSoonNotification(Notification):
    type = NotificationType.TASK_DUE_SOON

    def __init__(self, task: ActionTask, days_left: int):
        self.obj = task
        self.days_left = days_left

    def get_context(self):
        return dict(task=self.obj.get_notification_context(), days_left=self.days_left)

    def generate_notifications(self, action_contacts: typing.List[Person]):
        for person in action_contacts:
            days = self.notification_last_sent(person)
            if days is not None:
                if days < MINIMUM_NOTIFICATION_PERIOD:
                    # We don't want to remind too often
                    continue
                if self.days_left not in (1, 7, 30):
                    # If we have reminded about this before, let's only
                    # send a reminder if it's tomorrow, in a week or in a month
                    continue
            else:
                # If we have never reminded about this, send a notification
                # no matter how many days are left.
                pass

            self._queue_notification(person)


class NotEnoughTasksNotification(Notification):
    type = NotificationType.NOT_ENOUGH_TASKS

    def __init__(self, action: Action):
        self.obj = action

    def get_context(self):
        return dict(action=self.obj.get_notification_context())

    def generate_notifications(self):
        contacts = self.obj._contact_persons
        for person in contacts:
            days_since = self.notification_last_sent(person)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class ActionNotUpdatedNotification(Notification):
    type = NotificationType.ACTION_NOT_UPDATED

    def __init__(self, action: Action):
        self.obj = action

    def get_context(self):
        return dict(action=self.obj.get_notification_context(), last_updated_at=self.obj.updated_at)

    def generate_notifications(self):
        contacts = self.obj._contact_persons
        for person in contacts:
            days_since = self.notification_last_sent(person)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class NotificationEngine:
    def __init__(
        self, plan: Plan, force_to=None, limit=None, only_type=None, noop=False, only_email=None,
        ignore_actions=None
    ):
        self.plan = plan
        self.today = date.today()
        self.force_to = force_to
        self.limit = limit
        self.only_type = only_type
        self.noop = noop
        self.only_email = only_email
        self.ignore_actions = set(ignore_actions or [])

    def _fetch_data(self):
        qs = ActionTask.objects.filter(action__plan=self.plan)
        qs = qs.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        self.active_tasks = list(qs.order_by('due_at'))

        actions = self.plan.actions.select_related('status')
        for act in actions:
            act.plan = self.plan  # prevent DB query
            act._contact_persons = []  # same, filled in later
            if act.identifier in self.ignore_actions:
                act._ignore = True
            else:
                act._ignore = False
        self.actions_by_id = {act.id: act for act in actions}

        for task in self.active_tasks:
            task.action = self.actions_by_id[task.action_id]

        action_contacts = ActionContactPerson.objects.filter(action__in=actions).select_related('person')
        persons_by_id = {}
        for ac in action_contacts:
            if ac.person_id not in persons_by_id:
                persons_by_id[ac.person_id] = ac.person
                ac.person._notifications = {}
            action = self.actions_by_id[ac.action_id]
            action._contact_persons.append(persons_by_id[ac.person_id])
        self.persons_by_id = persons_by_id

    def was_notification_sent(self, action: Action, type: str) -> bool:
        return action.sent_notifications.filter(type=type).exists()

    def generate_task_notifications(self, task: ActionTask):
        assert task.state not in (ActionTask.CANCELLED, ActionTask.COMPLETED)
        assert not task.completed_at

        diff = (task.due_at - self.today).days
        if diff < 0:
            # Task is late
            notif = TaskLateNotification(task, -diff)
        elif diff <= TASK_DUE_SOON_DAYS:
            # Task DL is coming
            notif = TaskDueSoonNotification(task, diff)
        else:
            return
        notif.generate_notifications(task.action._contact_persons)

    def make_action_notifications(self, action: Action):
        # Generate a notification if action doesn't have at least
        # one active task with DLs within 365 days
        N_DAYS = 365
        TASK_COUNT = 1
        # Also when the action has not been updated in 90 days
        LAST_UPDATED_DAYS = 90

        active_tasks = action.tasks.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        today = date.today()
        count = 0
        for task in active_tasks:
            diff = (task.due_at - today).days
            if diff <= N_DAYS:
                count += 1
        if count < TASK_COUNT:
            notif = NotEnoughTasksNotification(action)
            notif.generate_notifications()

        if today - action.updated_at.date() >= timedelta(days=LAST_UPDATED_DAYS):
            notif = ActionNotUpdatedNotification(action)
            notif.generate_notifications()

        return

    def generate_notifications(self):
        self._fetch_data()

        for task in self.active_tasks:
            if task.action._ignore or not task.action.is_active():
                continue
            self.generate_task_notifications(task)

        for action in self.actions_by_id.values():
            if action._ignore or not action.is_active():
                continue
            self.make_action_notifications(action)

        base_template = self.plan.notification_base_template
        templates_by_type = {t.type: t for t in base_template.templates.all()}
        notification_count = 0

        for person in self.persons_by_id.values():
            if self.only_email and person.email != self.only_email:
                continue
            for ttype, notifications in person._notifications.items():
                if self.only_type and ttype != self.only_type:
                    continue
                template = templates_by_type.get(ttype)
                if template is None:
                    logger.error('No template for %s' % ttype)
                    continue

                cb_qs = base_template.content_blocks.filter(Q(template__isnull=True) | Q(template=template))
                content_blocks = {cb.identifier: Markup(cb.content) for cb in cb_qs}

                context = {
                    'items': [x.get_context() for x in notifications],
                    'person': person.get_notification_context(),
                    'content_blocks': content_blocks,
                }
                rendered = template.render(context)
                if self.force_to:
                    to_email = self.force_to
                else:
                    to_email = person.email
                msg = EmailMessage(
                    rendered['subject'],
                    rendered['html_body'],
                    'Helsingin ilmastovahti <noreply@ilmastovahti.fi>',
                    [to_email]
                )
                msg.content_subtype = "html"  # Main content is now text/html

                nstr = []
                for n in notifications:
                    if isinstance(n.obj, ActionTask):
                        s = '\t%s: %s' % (n.obj.action, n.obj)
                    else:
                        s = '\t%s' % str(n.obj)
                    nstr.append(s)
                logger.info('Sending notification %s to %s\n%s' % (ttype, to_email, '\n'.join(nstr)))

                if not self.noop:
                    msg.send()
                if not self.force_to and not self.noop:
                    for n in notifications:
                        n.mark_sent(person)
                notification_count += 1
                if self.limit and notification_count >= self.limit:
                    return


class ActionNotification:
    def __init__(self, action, type, message):
        self.action = action
        self.message = message
        self.type = type


class Command(BaseCommand):
    help = 'Recalculates statuses and completions for all actions'

    def add_arguments(self, parser):
        type_choices = [x.identifier for x in NotificationType]
        parser.add_argument('--plan', type=str, help='Identifier of the action plan')
        parser.add_argument('--force-to', type=str, help='Rewrite the To field and send all emails to this address')
        parser.add_argument('--limit', type=int, help='Do not send more than this many emails')
        parser.add_argument('--only-type', type=str, choices=type_choices, help='Send only notifications of this type')
        parser.add_argument('--only-email', type=str, help='Send only the notifications that go this email')
        parser.add_argument('--ignore-actions', type=str, help='Comma-separated list of action identifiers to ignore')
        parser.add_argument('--noop', action='store_true', help='Do not actually send the emails')

    def handle(self, *args, **options):
        if not options['plan']:
            raise CommandError('No plan supplied')

        activate(settings.LANGUAGES[0][0])

        plan = Plan.objects.get(identifier=options['plan'])
        ignore_actions = []
        for act_id in options['ignore_actions'].split(','):
            act = plan.actions.filter(identifier=act_id).first()
            if act is None:
                raise CommandError('Action %s does not exist' % act_id)
            ignore_actions.append(act.identifier)

        engine = NotificationEngine(
            plan,
            force_to=options['force_to'],
            limit=options['limit'],
            only_type=options['only_type'],
            noop=options['noop'],
            only_email=options['only_email'],
            ignore_actions=ignore_actions
        )
        engine.generate_notifications()
