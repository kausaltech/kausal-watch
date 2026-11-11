from __future__ import annotations

import logging

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import override
from wagtail.admin.admin_url_finder import AdminURLFinder
from wagtail.admin.mail import EmailNotificationMixin, Notifier, WorkflowStateApprovalEmailNotifier
from wagtail.models import TaskState

from aplans.email_sender import EmailSender

from users.models import User

from .models import Action, ActionContactPerson

logger = logging.getLogger(__name__)


class BaseActionModeratorApprovalTaskStateEmailNotifier(EmailNotificationMixin, Notifier):
    """A base notifier to send updates for UserApprovalTask events."""

    notification: str

    def __init__(self):
        # Allow TaskState to send notifications
        super().__init__((TaskState,))

    def get_context(self, task_state, **kwargs):
        context = super().get_context(task_state, **kwargs)
        content_object = task_state.workflow_state.content_object
        context['object'] = content_object
        context['plan'] = getattr(content_object, 'plan', None)
        context['task'] = task_state.task.specific
        # Without a user, the finder skips the permission check; the recipients are not logged in
        context['admin_url_finder'] = AdminURLFinder(None)
        context['model_name'] = content_object._meta.verbose_name
        return context

    def get_valid_recipients(self, instance, **kwargs):
        # The stock implementation has a limited selection of notification types based on what's available in Wagtail's
        # model. We will assume that cancellation of a submitted item can reuse the same settings as the original submit.
        actual_notification = self.notification
        if self.notification == 'cancelled':
            self.notification = 'submitted'
        result = super().get_valid_recipients(instance, **kwargs)
        self.notification = actual_notification
        return result

    def get_recipient_users(self, task_state, **kwargs):
        # TODO
        action = task_state.workflow_state.content_object
        assert isinstance(action, Action)
        moderator_ids = action.contact_persons.filter(role=ActionContactPerson.Role.MODERATOR).values_list('person__user')
        return User.objects.filter(id__in=moderator_ids)

    def send_emails(self, template_set, context, recipients, **kwargs):
        """Overridden just to modify the From: and Reply-To: headers."""
        plan = context.get('plan', None)
        email_sender = EmailSender(plan=plan)
        subject = render_to_string(
            template_set['subject'],
            context,
        ).strip()

        for recipient in recipients:
            # update context with this recipient
            context['user'] = recipient

            # Translate text to the recipient language settings
            with override(
                recipient.wagtail_userprofile.get_preferred_language(),
            ):
                # Get email subject and content
                email_subject = render_to_string(
                    template_set['subject'],
                    context,
                ).strip()
                email_content = render_to_string(
                    template_set['text'],
                    context,
                ).strip()

            message = EmailMessage(
                subject=email_subject,
                body=email_content,
                to=[recipient.email],
            )
            email_sender.queue(message)
        try:
            num_sent = email_sender.send_all()
        except Exception:
            logger.exception(
                f'Failed to send notification emails with subject [{subject}].',
            )
            num_sent = 0
        return num_sent == len(recipients)


class ActionModeratorApprovalTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events."""

    notification = 'submitted'


class ActionModeratorCancelTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events."""

    notification = 'cancelled'


class WorkflowStateApprovalWithCommentEmailNotifier(WorkflowStateApprovalEmailNotifier):
    """A notifier to send email updates for WorkflowState approval events."""

    notification = 'approved'

    def __call__(self, instance, user, **kwargs):

        if not self.can_handle(instance, **kwargs):
            return False

        recipients = self.get_valid_recipients(instance, **kwargs)

        if not recipients:
            return True

        context = self.get_context(instance, **kwargs)
        comment = context.get('comment', None)
        self.notification = 'approved_comment' if comment else 'approved'
        template_set = self.get_template_set(instance, **kwargs)

        return self.send_notifications(template_set, context, recipients, **kwargs)

    # Override to add the comment to the context, can be removed if wagtail adds this
    def get_context(self, workflow_state, **kwargs):
        context = super().get_context(workflow_state, **kwargs)
        task_state = workflow_state.current_task_state.specific
        if task_state:
            context['comment'] = task_state.get_comment()
        return context

    def get_valid_recipients(self, instance, **kwargs):
        # The stock implementation has a limited selection of notification types based on what's available
        # in Wagtail's UserProfile model. We will assume that approval with comment can reuse the same settings
        # as the original submit.
        actual_notification = self.notification
        if self.notification == 'approved_comment':
            self.notification = 'approved'
        result = super().get_valid_recipients(instance, **kwargs)
        self.notification = actual_notification
        return result
