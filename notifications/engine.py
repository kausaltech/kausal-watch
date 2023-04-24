from datetime import timedelta
from django.core.mail import EmailMessage
from django.db.models import Q
from django.utils import translation
from logging import getLogger
from markupsafe import Markup
from sentry_sdk import capture_exception

from actions.models import Plan, ActionTask, Action, ActionContactPerson
from feedback.models import UserFeedback
from indicators.models import Indicator, IndicatorContactPerson
from .mjml import render_mjml_from_template
from .notifications import (
    ActionNotUpdatedNotification, NotEnoughTasksNotification, TaskDueSoonNotification, TaskLateNotification,
    UpdatedIndicatorValuesDueSoonNotification, UpdatedIndicatorValuesLateNotification,
    UserFeedbackReceivedNotification,
)

logger = getLogger(__name__)

TASK_DUE_SOON_DAYS = 30
UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS = 30


class InvalidStateException(Exception):
    pass


class NotificationEngine:
    def __init__(
        self, plan: Plan, force_to=None, limit=None, only_type=None, noop=False, only_email=None,
        ignore_actions=None, ignore_indicators=None, dump=None, now=None
    ):
        if now is None:
            now = plan.now_in_local_timezone()

        self.plan = plan
        self.now = now
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

        diff = (task.due_at - self.now.date()).days
        if diff < 0:
            # Task is late
            notif = TaskLateNotification(self.plan, task, -diff)
        elif diff <= TASK_DUE_SOON_DAYS:
            # Task DL is coming
            notif = TaskDueSoonNotification(self.plan, task, diff)
        else:
            return
        notif.generate_notifications(task.action._notification_recipients, now=self.now)

    def generate_indicator_notifications(self, indicator: Indicator):
        if indicator.updated_values_due_at is None:
            return
        diff = (indicator.updated_values_due_at - self.now.date()).days
        if diff < 0:
            # Updated indicator values are late
            notif = UpdatedIndicatorValuesLateNotification(self.plan, indicator, -diff)
        elif diff <= UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS:
            # Updated indicator values DL is coming
            notif = UpdatedIndicatorValuesDueSoonNotification(self.plan, indicator, diff)
        else:
            return
        notif.generate_notifications(indicator._notification_recipients, now=self.now)

    def generate_action_notifications(self, action: Action):
        # Generate a notification if action doesn't have at least
        # one active task with DLs within 365 days
        N_DAYS = 365
        TASK_COUNT = 1
        # Also when the action has not been updated in the desired number of days
        LAST_UPDATED_DAYS = self.plan.get_action_days_until_considered_stale()

        active_tasks = action.tasks.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        count = 0
        for task in active_tasks:
            diff = (task.due_at - self.now.date()).days
            if diff <= N_DAYS:
                count += 1
        if count < TASK_COUNT:
            notif = NotEnoughTasksNotification(self.plan, action)
            notif.generate_notifications(now=self.now)

        if self.now.date() - action.updated_at.date() >= timedelta(days=LAST_UPDATED_DAYS):
            notif = ActionNotUpdatedNotification(self.plan, action)
            notif.generate_notifications(now=self.now)

    def generate_user_feedback_notifications(self, user_feedback: UserFeedback):
        notification = UserFeedbackReceivedNotification(self.plan, user_feedback)
        notification.generate_notifications(now=self.now)

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
