from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import prefetch_related_objects
from django.utils import translation

from anymail.exceptions import AnymailInvalidAddress, AnymailRecipientsRefused, AnymailRequestsAPIError
from sentry_sdk import capture_exception, capture_message, new_scope

from aplans.email_sender import EmailSender

from access_requests.models import AccessRequest
from actions.models import ActionContactPerson, ActionTask
from actions.models.public_user import PublicUser
from indicators.models import IndicatorContactPerson

from .mjml import render_mjml_from_template
from .models import DEFAULT_BRAND_DARK_COLOR, DEFAULT_FONT_FAMILY, ManuallyScheduledNotificationTemplate
from .notifications import (
    AccessRequestsReceivedNotification,
    ActionNotUpdatedNotification,
    ManuallyScheduledNotification,
    NotEnoughTasksNotification,
    NotificationType,
    PledgeParticipantSignupNotification,
    TaskDueSoonNotification,
    TaskLateNotification,
    UpdatedIndicatorValuesDueSoonNotification,
    UpdatedIndicatorValuesLateNotification,
    UserFeedbackReceivedNotification,
)
from .queue import NotificationQueue
from .recipients import PersonRecipient
from .utils import NonPublicURLError, public_urls_required, validate_notification_context_urls

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from actions.models import Action, Plan
    from feedback.models import UserFeedback
    from indicators.models import Indicator

    from .models import AutomaticNotificationTemplate, BaseTemplate
    from .notifications import Notification
    from .queue import NotificationQueueItem
    from .recipients import NotificationRecipient

# The admin interface's look, for emails about the admin rather than the plan.
ADMIN_THEME = {
    'brand_dark_color': DEFAULT_BRAND_DARK_COLOR,
    'font_family': None,
    'font_family_with_fallback': DEFAULT_FONT_FAMILY,
    'font_css_url': None,
    'link_in_brand_bg_color': '#ffffff',
}

# How many distinct reasons for skipped messages one Sentry report lists.
MAX_REPORTED_SKIP_REASONS = 3

# Mail provider statuses that refuse the request as a whole (credentials, rate limits), so every
# later message in the run would fail the same way.
PROVIDER_WIDE_CLIENT_ERRORS = frozenset({401, 403, 429})

logger = getLogger(__name__)

TASK_DUE_SOON_DAYS = 30
UPDATED_INDICATOR_VALUES_DUE_SOON_DAYS = 30


class InvalidStateException(Exception):  # noqa: N818
    pass


@dataclass(frozen=True)
class OutgoingMessage:
    msg: EmailMessage
    queue_items: Sequence[NotificationQueueItem]
    recipient: NotificationRecipient


def rejects_only_this_message(error: AnymailInvalidAddress | AnymailRecipientsRefused | AnymailRequestsAPIError) -> bool:
    """
    Tell whether a mail provider error concerns only the message being sent.

    Such a message (e.g. one with an invalid recipient address) is skipped so that it does not stop
    the run. Network errors, server errors and errors with the provider account affect every message.
    """
    if not isinstance(error, AnymailRequestsAPIError):
        return True
    status_code = error.status_code
    if status_code is None:
        return False
    return 400 <= status_code < 500 and status_code not in PROVIDER_WIDE_CLIENT_ERRORS


class NotificationEngine:
    def __init__(
        self,
        plan: Plan,
        force_to=None,
        limit=None,
        only_type=None,
        noop=False,
        only_email=None,
        ignore_actions=None,
        ignore_indicators=None,
        dump=None,
        now=None,
    ):
        if now is None:
            now = plan.now_in_local_timezone()

        # Every message builds plan and object URLs from the plan's domains.
        prefetch_related_objects([plan], 'domains')
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

    def _fetch_data(self) -> None:
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
        notif: TaskDueSoonNotification | TaskLateNotification
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
                self.action_contact_person_recipients,
                self.indicator_contact_person_recipients,
                self.plan_admin_recipients,
                self.organization_plan_admin_recipients,
                action=task.action,
            )
            notif.generate_notifications(self, recipients, now=self.now)

    def generate_indicator_notifications(self, indicator: Indicator):
        if indicator.updated_values_due_at is None:
            return
        diff = (indicator.updated_values_due_at - self.now.date()).days
        notif: UpdatedIndicatorValuesDueSoonNotification | UpdatedIndicatorValuesLateNotification
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
                self.action_contact_person_recipients,
                self.indicator_contact_person_recipients,
                self.plan_admin_recipients,
                self.organization_plan_admin_recipients,
                indicator=indicator,
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
        notif: NotEnoughTasksNotification | ActionNotUpdatedNotification
        if count < TASK_COUNT:
            notif = NotEnoughTasksNotification(self.plan, action)
            template = self.templates_by_type.get(NotificationType.NOT_ENOUGH_TASKS.identifier)
            if template:
                recipients = template.get_recipients(
                    self.action_contact_person_recipients,
                    self.indicator_contact_person_recipients,
                    self.plan_admin_recipients,
                    self.organization_plan_admin_recipients,
                    action=action,
                )
                notif.generate_notifications(self, recipients, now=self.now)

        if self.now.date() - action.updated_at.date() >= timedelta(days=LAST_UPDATED_DAYS):
            notif = ActionNotUpdatedNotification(self.plan, action)
            template = self.templates_by_type.get(NotificationType.ACTION_NOT_UPDATED.identifier)
            if template:
                recipients = template.get_recipients(
                    self.action_contact_person_recipients,
                    self.indicator_contact_person_recipients,
                    self.plan_admin_recipients,
                    self.organization_plan_admin_recipients,
                    action=action,
                )
                notif.generate_notifications(self, recipients, now=self.now)

    def generate_user_feedback_notifications(self, user_feedback: UserFeedback):
        notification = UserFeedbackReceivedNotification(self.plan, user_feedback)
        template = self.templates_by_type.get(NotificationType.USER_FEEDBACK_RECEIVED.identifier)
        if template:
            recipients = template.get_recipients(
                self.action_contact_person_recipients,
                self.indicator_contact_person_recipients,
                self.plan_admin_recipients,
                self.organization_plan_admin_recipients,
            )
            notification.generate_notifications(self, recipients, now=self.now)

    def generate_pledge_signup_notifications(self, public_user: PublicUser):
        notification = PledgeParticipantSignupNotification(self.plan, public_user)
        template = self.templates_by_type.get(NotificationType.PLEDGE_PARTICIPANT_SIGNUP.identifier)
        if template:
            recipients = template.get_recipients(
                self.action_contact_person_recipients,
                self.indicator_contact_person_recipients,
                self.plan_admin_recipients,
                self.organization_plan_admin_recipients,
            )
            notification.generate_notifications(self, recipients, now=self.now)

    def generate_access_request_notifications(self):
        notification_type = NotificationType.ACCESS_REQUESTS_RECEIVED
        identifier = notification_type.identifier
        if not notification_type.is_enabled_for(self.plan.features):
            return
        if self.only_type and self.only_type != identifier:
            return
        template = self.templates_by_type.get(identifier)
        if template is None:
            return
        pending = AccessRequest.objects.qs.filter(plan=self.plan).pending()
        waiting_count = pending.count()
        recipients = template.get_recipients(
            self.action_contact_person_recipients,
            self.indicator_contact_person_recipients,
            self.plan_admin_recipients,
            self.organization_plan_admin_recipients,
        )
        for access_request in pending.exclude(sent_notifications__type=identifier):
            notification = AccessRequestsReceivedNotification(self.plan, access_request, waiting_count)
            notification.generate_notifications(self, recipients, now=self.now)

    def generate_manually_scheduled_notification(self, template: ManuallyScheduledNotificationTemplate):
        notification = ManuallyScheduledNotification(self.plan, template)
        recipients = template.get_recipients(
            self.action_contact_person_recipients,
            self.indicator_contact_person_recipients,
            self.plan_admin_recipients,
            self.organization_plan_admin_recipients,
        )
        notification.generate_notifications(self, recipients, now=self.now)

    def render(self, template, context, language_code=None, plan_theme=True):
        if not language_code:
            language_code = self.plan.primary_language

        logger.debug('Rendering template for notification %s' % template.type)

        rendered = {}
        with translation.override(language_code):
            theme_context = template.base.get_notification_context() if plan_theme else {'theme': ADMIN_THEME}
            context = dict(
                title=template.subject,
                **theme_context,
                **context,
            )
            validate_notification_context_urls(context, allow_localhost=not public_urls_required())

            rendered['html_body'] = render_mjml_from_template(
                template.type,
                context,
                dump=self.dump,
            )
            rendered['subject'] = template.subject + ' | ' + context['site']['title']

        return rendered

    def _render_message(
        self,
        queue_items: Sequence[NotificationQueueItem],
        base_template: BaseTemplate,
        template: AutomaticNotificationTemplate | ManuallyScheduledNotificationTemplate,
        recipient_context: dict,
    ) -> dict:
        notification = queue_items[0].notification
        content_blocks = notification.get_content_blocks(base_template, template)

        context = {
            'items': [item.notification.get_context() for item in queue_items],
            'content_blocks': content_blocks,
            'site': dict(self.site_context),
            **recipient_context,
        }

        if not notification.uses_plan_theme:
            # Presented as coming from the admin interface: no plan logo, and the header
            # leads to the admin rather than the plan's public site.
            context.pop('logo', None)
            context['site'] = {
                'title': f'Kausal Watch · {self.plan.name_i18n}',
                'view_url': settings.ADMIN_BASE_URL,
            }
            context['plan_name'] = self.plan.name_i18n

        # rendered = self.render(template, context, language_code=recipient.get_preferred_language())
        # For now, use primary language of plan instead of the recipient's preferred language
        return self.render(template, context, plan_theme=notification.uses_plan_theme)

    def generate_notifications(self):  # noqa: C901
        self.queue = NotificationQueue()
        self.action_contact_person_recipients: dict[int, Sequence[NotificationRecipient]] = {}
        self.indicator_contact_person_recipients: dict[int, Sequence[NotificationRecipient]] = {}
        self.organization_plan_admin_recipients: dict[int, Sequence[NotificationRecipient]] = {}
        self.plan_admin_recipients = []

        self._fetch_data()

        base_template = self.plan.notification_base_template
        # The same for every message, so resolved once; a plan without a public URL fails here, before anything is sent.
        self.site_context = self.plan.get_site_notification_context()
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

        client_id = self.plan.primary_client_id
        signup_type = NotificationType.PLEDGE_PARTICIPANT_SIGNUP
        signup_identifier = signup_type.identifier
        if (
            client_id is not None
            and signup_type.is_enabled_for(self.plan.features)
            and signup_identifier in self.templates_by_type
            and (not self.only_type or self.only_type == signup_identifier)
        ):
            participants = (
                PublicUser.objects
                .filter(client_id=client_id, email__isnull=False)
                .exclude(sent_notifications__type=signup_identifier)
                .order_by('email_verified_at')
            )
            for public_user in participants:
                self.generate_pledge_signup_notifications(public_user)

        self.generate_access_request_notifications()

        for manually_scheduled_notification_template in ManuallyScheduledNotificationTemplate.objects.filter(
            base__plan=self.plan
        ):
            self.generate_manually_scheduled_notification(manually_scheduled_notification_template)

        self.skipped_messages: list[str] = []
        try:
            self._send_notifications(base_template)
        finally:
            self._report_skipped_messages()

    def _report_skipped_messages(self) -> None:
        if not self.skipped_messages:
            return
        # The cause is usually shared by every message (e.g. a misconfigured URL setting), so report it once.
        # The reasons name each message's own URLs; the fingerprint keeps the runs in one Sentry issue per plan.
        reasons = sorted(set(self.skipped_messages))
        shown = '; '.join(reasons[:MAX_REPORTED_SKIP_REASONS])
        if len(reasons) > MAX_REPORTED_SKIP_REASONS:
            shown += f'; and {len(reasons) - MAX_REPORTED_SKIP_REASONS} more'
        with new_scope() as scope:
            scope.fingerprint = ['notifications-skipped-messages', self.plan.identifier]
            capture_message(
                f'{len(self.skipped_messages)} notification message(s) for plan {self.plan.identifier} were skipped: {shown}',
                level='error',
            )

    def _send_notifications(self, base_template: BaseTemplate) -> None:
        """
        Send each queued message as soon as it is rendered, and record it as sent once it has gone out.

        A message that cannot be built for a known reason (a non-public URL), that the mail backend
        does not accept, or that the mail provider rejects on its own (e.g. for an invalid recipient
        address) is skipped unrecorded and reported once per run; the plan's run completes, so it is
        retried on the plan's next daily run. Any other error, including a failing connection or a
        provider error that would affect every message, stops the run; the daily command then
        retries the plan on its next hourly pass, and messages already sent stay recorded.

        Delivery is at least once: a message sent just before a failure to record it goes out again.
        """
        with EmailSender(plan=self.plan) as email_sender:
            for count, outgoing in enumerate(self._build_messages(base_template), start=1):
                if not self.noop:
                    self._deliver(email_sender, outgoing)
                if self.limit and count >= self.limit:
                    return

    def _deliver(self, email_sender: EmailSender, outgoing: OutgoingMessage) -> None:
        try:
            accepted = email_sender.send(outgoing.msg)
        except (AnymailInvalidAddress, AnymailRecipientsRefused, AnymailRequestsAPIError) as e:
            if not rejects_only_this_message(e):
                raise
            # Left unrecorded, so it is tried again on the next run.
            logger.error(str(e))
            self.skipped_messages.append(f'The mail provider rejected the message to {outgoing.msg.to}: {e}')
            return
        if not accepted:
            # Left unrecorded, so it is tried again on the next run.
            self.skipped_messages.append(f'The mail backend did not accept the message to {outgoing.msg.to}')
            return
        if self.force_to:
            # Only a copy went out; the real recipient still needs the message.
            return
        self._mark_sent(outgoing.queue_items, outgoing.recipient)

    def _build_messages(self, base_template: BaseTemplate) -> Iterator[OutgoingMessage]:  # noqa: C901, PLR0912
        for recipient, items_for_type in self.queue.items_for_recipient.items():
            if self.only_email and recipient.get_email() != self.only_email:
                continue
            try:
                recipient_context = recipient.get_notification_context()
            except ValueError as e:
                capture_exception(e)
                logger.error(str(e))
                continue
            for notification_type, queue_items_by_identifier in items_for_type.items():
                for queue_items in queue_items_by_identifier.values():
                    ttype = notification_type.identifier
                    if self.only_type and ttype != self.only_type:
                        continue
                    template: AutomaticNotificationTemplate | ManuallyScheduledNotificationTemplate
                    if notification_type == NotificationType.MANUALLY_SCHEDULED:
                        manual_template = queue_items[0].notification.obj
                        assert isinstance(manual_template, ManuallyScheduledNotificationTemplate)
                        template = manual_template
                    else:
                        automatic_template = self.templates_by_type.get(ttype)
                        if automatic_template is None:
                            logger.debug('No template for %s' % ttype)
                            continue
                        template = automatic_template

                    # render() checks that every URL in the message is public. A message that fails is skipped
                    # unmarked so the others still go out; it is retried on the next run.
                    try:
                        rendered = self._render_message(queue_items, base_template, template, recipient_context)
                    except NonPublicURLError as e:
                        logger.error(str(e))
                        self.skipped_messages.append(str(e))
                        continue

                    if self.force_to:
                        to_email = self.force_to
                    else:
                        to_email = recipient.get_email()  # can be None if the recipient has no corresponding email address
                    if not to_email:
                        continue

                    msg = EmailMessage(
                        subject=rendered['subject'],
                        body=rendered['html_body'],
                        to=[to_email],
                    )
                    msg.content_subtype = 'html'  # Main content is now text/html

                    nstr = []
                    for item in queue_items:
                        if isinstance(item.notification.obj, ActionTask):
                            s = '\t%s: %s' % (item.notification.obj.action, item.notification.obj)
                        else:
                            s = '\t%s' % str(item.notification.obj)
                        nstr.append(s)
                    logger.info('Sending notification %s to %s\n%s' % (ttype, to_email, '\n'.join(nstr)))
                    yield OutgoingMessage(msg=msg, queue_items=queue_items, recipient=recipient)

    def _mark_sent(self, queue_items: Sequence[NotificationQueueItem], recipient: NotificationRecipient) -> None:
        for item in queue_items:
            item.notification.mark_sent(recipient, now=self.now)

    def queue_notification(self, notification: Notification, recipient: NotificationRecipient):
        item = recipient.queue_item(notification)
        self.queue.push(item)
