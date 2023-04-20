from datetime import timedelta
from django.core.mail import EmailMessage
from django.db.models import Q
from django.utils import translation
from logging import getLogger
from markupsafe import Markup
from sentry_sdk import capture_exception
from typing import Dict, Sequence

from .mjml import render_mjml_from_template
from .models import NotificationType
from .notifications import (
    ActionNotUpdatedNotification, Notification, NotEnoughTasksNotification, TaskDueSoonNotification,
    TaskLateNotification, UpdatedIndicatorValuesDueSoonNotification, UpdatedIndicatorValuesLateNotification,
    UserFeedbackReceivedNotification,
)
from .queue import NotificationQueue
from .recipients import NotificationRecipient, PersonRecipient
from actions.models import Plan, ActionTask, Action, ActionContactPerson
from feedback.models import UserFeedback
from indicators.models import Indicator, IndicatorContactPerson

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

    def ignore_action(self, action):
        return action.identifier in self.ignore_actions

    def ignore_indicator(self, indicator):
        return indicator.identifier in self.ignore_indicators

    def _fetch_data(self):
        active_tasks = ActionTask.objects.filter(action__plan=self.plan)
        active_tasks = active_tasks.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))
        self.active_tasks = list(active_tasks.order_by('due_at'))

        indicators = self.plan.indicators.all()
        self.indicators = list(indicators.order_by('updated_values_due_at'))

        actions = self.plan.actions.select_related('status')
        for act in actions:
            act.plan = self.plan  # prevent DB query
        self.actions_by_id = {act.id: act for act in actions}

        for indicator in indicators:
            indicator.plan = self.plan  # prevent DB query
        self.indicators_by_id = {indicator.id: indicator for indicator in indicators}

        for task in self.active_tasks:
            task.action = self.actions_by_id[task.action_id]

        action_contacts = ActionContactPerson.objects.filter(action__in=actions).select_related('person')
        for ac in action_contacts:
            recipients = list(self.action_contact_person_recipients.get(ac.action_id, []))
            recipients.append(PersonRecipient(ac.person))
            self.action_contact_person_recipients[ac.action_id] = recipients

        indicator_contacts = IndicatorContactPerson.objects.filter(indicator__in=indicators).select_related('person')
        for ic in indicator_contacts:
            recipients = list(self.indicator_contact_person_recipients.get(ic.indicator_id, []))
            recipients.append(PersonRecipient(ic.person))
            self.indicator_contact_person_recipients[ic.indicator_id] = recipients

        for org_plan_admin in self.plan.organization_plan_admins.all().select_related('person'):
            recipients = list(self.organization_plan_admin_recipients.get(org_plan_admin.organization_id, []))
            recipients.append(PersonRecipient(org_plan_admin.person))
            self.organization_plan_admin_recipients[org_plan_admin.organization_id] = recipients

        self.plan_admin_recipients = [PersonRecipient(person) for person in self.plan.general_admins.all()]

    def generate_task_notifications(self, task: ActionTask):
        if task.state in (ActionTask.CANCELLED, ActionTask.COMPLETED):
            raise InvalidStateException('Task %s in wrong state: %s' % (str(task), task.state))
        if task.completed_at:
            raise InvalidStateException('Task %s already completed' % (str(task),))

        diff = (task.due_at - self.now.date()).days
        if diff < 0:
            # Task is late
            notif = TaskLateNotification(self.plan, task, -diff)
            template = self.templates_by_type.get(NotificationType.TASK_LATE.identifier)
        elif diff <= TASK_DUE_SOON_DAYS:
            # Task DL is coming
            notif = TaskDueSoonNotification(self.plan, task, diff)
            template = self.templates_by_type.get(NotificationType.TASK_DUE_SOON.identifier)
        else:
            return
        if template:
            recipients = template.get_recipients(
                self.action_contact_person_recipients, self.indicator_contact_person_recipients,
                self.plan_admin_recipients, self.organization_plan_admin_recipients, action=task.action
            )
            notif.generate_notifications(self, recipients, now=self.now)

    def generate_indicator_notifications(self, indicator: Indicator):
        if indicator.updated_values_due_at is None:
            return
        diff = (indicator.updated_values_due_at - self.now.date()).days
        if diff < 0:
            # Updated indicator values are late
            notif = UpdatedIndicatorValuesLateNotification(self.plan, indicator, -diff)
            template = self.templates_by_type.get(NotificationType.UPDATED_INDICATOR_VALUES_LATE.identifier)
        elif diff <= UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS:
            # Updated indicator values DL is coming
            notif = UpdatedIndicatorValuesDueSoonNotification(self.plan, indicator, diff)
            template = self.templates_by_type.get(NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
        else:
            return
        if template:
            recipients = template.get_recipients(
                self.action_contact_person_recipients, self.indicator_contact_person_recipients,
                self.plan_admin_recipients, self.organization_plan_admin_recipients, indicator=indicator
            )
            notif.generate_notifications(self, recipients, now=self.now)

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
            template = self.templates_by_type.get(NotificationType.NOT_ENOUGH_TASKS.identifier)
            if template:
                recipients = template.get_recipients(
                    self.action_contact_person_recipients, self.indicator_contact_person_recipients,
                    self.plan_admin_recipients, self.organization_plan_admin_recipients, action=action
                )
                notif.generate_notifications(self, recipients, now=self.now)

        if self.now.date() - action.updated_at.date() >= timedelta(days=LAST_UPDATED_DAYS):
            notif = ActionNotUpdatedNotification(self.plan, action)
            template = self.templates_by_type.get(NotificationType.ACTION_NOT_UPDATED.identifier)
            if template:
                recipients = template.get_recipients(
                    self.action_contact_person_recipients, self.indicator_contact_person_recipients,
                    self.plan_admin_recipients, self.organization_plan_admin_recipients, action=action
                )
                notif.generate_notifications(self, recipients, now=self.now)

    def generate_user_feedback_notifications(self, user_feedback: UserFeedback):
        notification = UserFeedbackReceivedNotification(self.plan, user_feedback)
        template = self.templates_by_type.get(NotificationType.USER_FEEDBACK_RECEIVED.identifier)
        if template:
            recipients = template.get_recipients(
                self.action_contact_person_recipients, self.indicator_contact_person_recipients,
                self.plan_admin_recipients, self.organization_plan_admin_recipients
            )
            notification.generate_notifications(self, recipients, now=self.now)

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
        self.queue = NotificationQueue()
        self.action_contact_person_recipients: Dict[int, Sequence[NotificationRecipient]] = {}
        self.indicator_contact_person_recipients: Dict[int, Sequence[NotificationRecipient]] = {}
        self.organization_plan_admin_recipients: Dict[int, Sequence[NotificationRecipient]] = {}
        self.plan_admin_recipients: Sequence[NotificationRecipient] = []

        self._fetch_data()

        base_template = self.plan.notification_base_template
        self.templates_by_type = {t.type: t for t in base_template.templates.all()}

        for task in self.active_tasks:
            if self.ignore_action(task.action) or not task.action.is_active():
                continue
            try:
                self.generate_task_notifications(task)
            except InvalidStateException as e:
                capture_exception(e)
                logger.error(str(e))

        for indicator in self.indicators_by_id.values():
            if not self.ignore_indicator(indicator):
                self.generate_indicator_notifications(indicator)

        for action in self.actions_by_id.values():
            if not self.ignore_action(action) and action.is_active():
                self.generate_action_notifications(action)

        for user_feedback in self.plan.user_feedbacks.all():
            self.generate_user_feedback_notifications(user_feedback)

        from_address = base_template.from_address or 'noreply@kausal.tech'
        from_name = base_template.from_name or 'Kausal'
        email_from = '%s <%s>' % (from_name, from_address)
        reply_to = [base_template.reply_to] if base_template.reply_to else None

        notification_count = 0

        for recipient, items_for_type in self.queue.items_for_recipient.items():
            if self.only_email and recipient.get_email() != self.only_email:
                continue
            for notification_type, queue_items in items_for_type.items():
                ttype = notification_type.identifier
                if self.only_type and ttype != self.only_type:
                    continue
                template = self.templates_by_type.get(ttype)
                if template is None:
                    logger.debug('No template for %s' % ttype)
                    continue

                cb_qs = base_template.content_blocks.filter(Q(template__isnull=True) | Q(template=template))
                content_blocks = {cb.identifier: Markup(cb.content) for cb in cb_qs}

                context = {
                    'items': [item.notification.get_context() for item in queue_items],
                    'content_blocks': content_blocks,
                    'site': self.plan.get_site_notification_context(),
                    **recipient.get_notification_context(),
                }

                # rendered = self.render(template, context, language_code=recipient.get_preferred_language())
                # For now, use primary language of plan instead of the recipient's preferred language
                rendered = self.render(template, context)

                if self.force_to:
                    to_email = self.force_to
                else:
                    to_email = recipient.get_email()  # can be None if the recipient has no corresponding email address
                if not to_email:
                    continue

                msg = EmailMessage(
                    subject=rendered['subject'],
                    body=rendered['html_body'],
                    from_email=email_from,
                    to=[to_email],
                    reply_to=reply_to,
                )
                msg.content_subtype = "html"  # Main content is now text/html

                nstr = []
                for item in queue_items:
                    if isinstance(item.notification.obj, ActionTask):
                        s = '\t%s: %s' % (item.notification.obj.action, item.notification.obj)
                    else:
                        s = '\t%s' % str(item.notification.obj)
                    nstr.append(s)
                logger.info('Sending notification %s to %s\n%s' % (ttype, to_email, '\n'.join(nstr)))

                if not self.noop:
                    msg.send()
                if not self.force_to and not self.noop:
                    for item in queue_items:
                        item.notification.mark_sent(recipient)
                notification_count += 1
                if self.limit and notification_count >= self.limit:
                    return

    def queue_notification(self, notification: Notification, recipient: NotificationRecipient):
        item = recipient.queue_item(notification)
        self.queue.push(item)
