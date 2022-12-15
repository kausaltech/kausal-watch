import typing
from datetime import date, timedelta

from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone, translation
from markupsafe import Markup
from sentry_sdk import capture_exception

from actions.models import Plan, ActionTask, Action, ActionContactPerson
from feedback.models import UserFeedback
from indicators.models import Indicator, IndicatorContactPerson
from people.models import Person
from notifications.models import NotificationType
from notifications.mjml import render_mjml_from_template

from logging import getLogger


logger = getLogger(__name__)


MINIMUM_NOTIFICATION_PERIOD = 5  # days
TASK_DUE_SOON_DAYS = 30
UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS = 30


class InvalidStateException(Exception):
    pass


class Notification:
    type: NotificationType
    plan: Plan
    obj: typing.Union[Action, ActionTask, Indicator]

    def __init__(self, type: NotificationType, plan: Plan, obj):
        self.type = type
        self.plan = plan
        self.obj = obj

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


class DeadlinePassedNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_late: int):
        super().__init__(type, plan, obj)
        self.days_late = days_late

    def generate_notifications(self, contacts: typing.List[Person]):
        for person in contacts:
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


class TaskLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_late: int):
        super().__init__(NotificationType.TASK_LATE, plan, task, days_late)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_late=self.days_late)


class UpdatedIndicatorValuesLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_late: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_LATE, plan, indicator, days_late)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_late=self.days_late)


class DeadlineSoonNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_left: int):
        super().__init__(type, plan, obj)
        self.days_left = days_left

    def generate_notifications(self, contacts: typing.List[Person]):
        for person in contacts:
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


class TaskDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_left: int):
        super().__init__(NotificationType.TASK_DUE_SOON, plan, task, days_left)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_left=self.days_left)


class UpdatedIndicatorValuesDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_left: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON, plan, indicator, days_left)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_left=self.days_left)


class NotEnoughTasksNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.NOT_ENOUGH_TASKS, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan))

    def generate_notifications(self):
        contacts = self.obj._notification_recipients
        for person in contacts:
            days_since = self.notification_last_sent(person)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class ActionNotUpdatedNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.ACTION_NOT_UPDATED, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan), last_updated_at=self.obj.updated_at)

    def generate_notifications(self):
        contacts = self.obj._notification_recipients
        for person in contacts:
            days_since = self.notification_last_sent(person)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class UserFeedbackReceivedNotification(Notification):
    def __init__(self, plan: Plan, user_feedback: UserFeedback):
        super().__init__(NotificationType.USER_FEEDBACK_RECEIVED, plan, user_feedback)

    def get_context(self):
        return {'user_feedback': self.obj}

    def generate_notifications(self):
        for person in self.obj._notification_recipients:
            if self.notification_last_sent(person) is None:
                self._queue_notification(person)


class NotificationEngine:
    def __init__(
        self, plan: Plan, force_to=None, limit=None, only_type=None, noop=False, only_email=None,
        ignore_actions=None, ignore_indicators=None, dump=None
    ):
        self.plan = plan
        self.today = date.today()
        self.force_to = force_to
        self.limit = limit
        self.only_type = only_type
        self.noop = noop
        self.only_email = only_email
        self.ignore_actions = set(ignore_actions or [])
        self.ignore_indicators = set(ignore_indicators or [])
        self.dump = dump

    def _fetch_data(self):
        active_tasks = ActionTask.objects.filter(action__plan=self.plan)
        active_tasks = active_tasks.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        self.active_tasks = list(active_tasks.order_by('due_at'))

        indicators = self.plan.indicators.all()
        self.indicators = list(indicators.order_by('updated_values_due_at'))

        actions = self.plan.actions.select_related('status')
        for act in actions:
            act.plan = self.plan  # prevent DB query
            act._notification_recipients = []  # same, filled in later
            if act.identifier in self.ignore_actions:
                act._ignore = True
            else:
                act._ignore = False
        self.actions_by_id = {act.id: act for act in actions}

        for indicator in indicators:
            indicator.plan = self.plan  # prevent DB query
            indicator._notification_recipients = []  # same, filled in later
            if indicator.identifier in self.ignore_indicators:
                indicator._ignore = True
            else:
                indicator._ignore = False
        self.indicators_by_id = {indicator.id: indicator for indicator in indicators}

        for task in self.active_tasks:
            task.action = self.actions_by_id[task.action_id]

        persons_by_id = {}

        action_contacts = ActionContactPerson.objects.filter(action__in=actions).select_related('person')
        for ac in action_contacts:
            if ac.person_id not in persons_by_id:
                persons_by_id[ac.person_id] = ac.person
                ac.person._notifications = {}
            action = self.actions_by_id[ac.action_id]
            action._notification_recipients.append(persons_by_id[ac.person_id])

        indicator_contacts = IndicatorContactPerson.objects.filter(indicator__in=indicators).select_related('person')
        for ic in indicator_contacts:
            if ic.person_id not in persons_by_id:
                persons_by_id[ic.person_id] = ic.person
                ic.person._notifications = {}
            indicator = self.indicators_by_id[ic.indicator_id]
            indicator._notification_recipients.append(persons_by_id[ic.person_id])

        admin_people = []
        for action in self.actions_by_id.values():
            admin_people += self.ensure_action_notification_recipient(action)
        for indicator in self.indicators_by_id.values():
            admin_people += self.ensure_indicator_notification_recipient(indicator)
        for person in admin_people:
            persons_by_id[person.id] = person
        self.persons_by_id = persons_by_id

        for person in self.plan.general_admins.all():
            if person.id not in persons_by_id:
                persons_by_id[person.id] = person
                person._notifications = {}

        self.user_feedbacks_by_id = {}
        for user_feedback in self.plan.user_feedbacks.all():
            user_feedback._notification_recipients = [
                persons_by_id[person.id] for person in self.plan.general_admins.all()
            ]
            self.user_feedbacks_by_id[user_feedback.id] = user_feedback

    def ensure_action_notification_recipient(self, action):
        if action._notification_recipients:
            return []
        organizations = set((p.organization for p in action.responsible_parties.all()))
        organizations.add(action.primary_org)
        people = [opa.person for opa in self.plan.organization_plan_admins.filter(organization__in=organizations)]
        for person in people:
            person._notifications = {}
        action._notification_recipients = people
        return people

    def ensure_indicator_notification_recipient(self, indicator):
        if indicator._notification_recipients:
            return []
        people = [opa.person for opa in self.plan.organization_plan_admins.filter(organization=indicator.organization)]
        for person in people:
            person._notifications = {}
        indicator._notification_recipients = people
        return people

    def generate_task_notifications(self, task: ActionTask):
        if task.state in (ActionTask.CANCELLED, ActionTask.COMPLETED):
            raise InvalidStateException('Task %s in wrong state: %s' % (str(task), task.state))
        if task.completed_at:
            raise InvalidStateException('Task %s already completed' % (str(task),))

        diff = (task.due_at - self.today).days
        if diff < 0:
            # Task is late
            notif = TaskLateNotification(self.plan, task, -diff)
        elif diff <= TASK_DUE_SOON_DAYS:
            # Task DL is coming
            notif = TaskDueSoonNotification(self.plan, task, diff)
        else:
            return
        notif.generate_notifications(task.action._notification_recipients)

    def generate_indicator_notifications(self, indicator: Indicator):
        if indicator.updated_values_due_at is None:
            return
        diff = (indicator.updated_values_due_at - self.today).days
        if diff < 0:
            # Updated indicator values are late
            notif = UpdatedIndicatorValuesLateNotification(self.plan, indicator, -diff)
        elif diff <= UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS:
            # Updated indicator values DL is coming
            notif = UpdatedIndicatorValuesDueSoonNotification(self.plan, indicator, diff)
        else:
            return
        notif.generate_notifications(indicator._notification_recipients)

    def generate_action_notifications(self, action: Action):
        # Generate a notification if action doesn't have at least
        # one active task with DLs within 365 days
        N_DAYS = 365
        TASK_COUNT = 1
        # Also when the action has not been updated in the desired number of days
        LAST_UPDATED_DAYS = self.plan.get_action_days_until_considered_stale()

        active_tasks = action.tasks.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        today = date.today()
        count = 0
        for task in active_tasks:
            diff = (task.due_at - today).days
            if diff <= N_DAYS:
                count += 1
        if count < TASK_COUNT:
            notif = NotEnoughTasksNotification(self.plan, action)
            notif.generate_notifications()

        if today - action.updated_at.date() >= timedelta(days=LAST_UPDATED_DAYS):
            notif = ActionNotUpdatedNotification(self.plan, action)
            notif.generate_notifications()

    def generate_user_feedback_notifications(self, user_feedback: UserFeedback):
        notification = UserFeedbackReceivedNotification(self.plan, user_feedback)
        notification.generate_notifications()

    def render(self, template, context, language_code=None):
        if not language_code:
            language_code = self.plan.primary_language

        logger.debug('Rendering template for notification %s' % template.type)

        rendered = {}
        with translation.override(language_code):
            context = dict(
                title=template.subject,
                **template.base.get_notification_context(),
                **context
            )

            rendered['html_body'] = render_mjml_from_template(
                template.type,
                context, dump=self.dump
            )
            rendered['subject'] = template.subject + ' | ' + context['site']['title']

        return rendered

    def generate_notifications(self):
        self._fetch_data()

        for task in self.active_tasks:
            if task.action._ignore or not task.action.is_active():
                continue
            try:
                self.generate_task_notifications(task)
            except InvalidStateException as e:
                capture_exception(e)
                logger.error(str(e))

        for indicator in self.indicators_by_id.values():
            if not indicator._ignore:
                self.generate_indicator_notifications(indicator)

        for action in self.actions_by_id.values():
            if action._ignore or not action.is_active():
                continue
            self.generate_action_notifications(action)

        for user_feedback in self.user_feedbacks_by_id.values():
            self.generate_user_feedback_notifications(user_feedback)

        base_template = self.plan.notification_base_template
        from_address = base_template.from_address or 'noreply@kausal.tech'
        from_name = base_template.from_name or 'Kausal'
        email_from = '%s <%s>' % (from_name, from_address)
        reply_to = [base_template.reply_to] if base_template.reply_to else None

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
                    logger.debug('No template for %s' % ttype)
                    continue

                cb_qs = base_template.content_blocks.filter(Q(template__isnull=True) | Q(template=template))
                content_blocks = {cb.identifier: Markup(cb.content) for cb in cb_qs}

                context = {
                    'items': [x.get_context() for x in notifications],
                    'person': person.get_notification_context(),
                    'content_blocks': content_blocks,
                    'site': self.plan.get_site_notification_context(),
                }

                rendered = self.render(template, context)

                if self.force_to:
                    to_email = self.force_to
                else:
                    to_email = person.email
                msg = EmailMessage(
                    subject=rendered['subject'],
                    body=rendered['html_body'],
                    from_email=email_from,
                    to=[to_email],
                    reply_to=reply_to,
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


class Command(BaseCommand):
    help = 'Recalculates statuses and completions for all actions'

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
