import logging

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import override
from wagtail.admin.mail import EmailNotificationMixin, Notifier
from wagtail_modeladmin.helpers import ModelAdminURLFinder
from wagtail.models import TaskState

from .models import Action, ActionContactPerson
from .action_admin import ActionAdmin
from aplans.email_sender import EmailSender
from users.models import User


logger = logging.getLogger(__name__)


class BaseActionModeratorApprovalTaskStateEmailNotifier(EmailNotificationMixin, Notifier):
    """A base notifier to send updates for UserApprovalTask events"""

    class AllowAllUsersAdminURLFinder(ModelAdminURLFinder):
        """
        Only to be used in contexts where permissions checks are impossible and not needed,
        currently when rendering emails to non-logged in users.
        """
        class PermissionHelper:
            def user_can_edit_obj(self, user, instance):
                return True
        url_helper = ActionAdmin().url_helper
        permission_helper = PermissionHelper

    def __init__(self):
        # Allow TaskState to send notifications
        super().__init__((TaskState,))

    def get_context(self, task_state, **kwargs):
        context = super().get_context(task_state, **kwargs)
        object = task_state.workflow_state.content_object
        context['object'] = object
        context['plan'] = object.plan if hasattr(object, 'plan') else None
        context['task'] = task_state.task.specific
        context['admin_url_finder'] = self.AllowAllUsersAdminURLFinder(None)
        context['model_name'] = object._meta.verbose_name
        return context

    def get_valid_recipients(self, instance, **kwargs):
        # The stock implementation has a limited selection of notification types based on what's available in Wagtail's UserProfile
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
        """ Overridden just to modify the From: and Reply-To: headers """
        from_email = None
        reply_to = None
        if 'plan' in context:
            plan = context.get('plan')
            base_template = plan.notification_base_template
            if base_template is not None:
                from_email = base_template.get_from_email()
                reply_to = [base_template.reply_to] if base_template.reply_to else None
        email_sender = EmailSender(from_email=from_email, reply_to=reply_to)
        subject = render_to_string(
            template_set["subject"], context
        ).strip()

        for recipient in recipients:
            # update context with this recipient
            context["user"] = recipient

            # Translate text to the recipient language settings
            with override(
                recipient.wagtail_userprofile.get_preferred_language()
            ):
                # Get email subject and content
                email_subject = render_to_string(
                    template_set["subject"], context
                ).strip()
                email_content = render_to_string(
                    template_set["text"], context
                ).strip()

            message = EmailMessage(
                subject=email_subject,
                body=email_content,
                to=[recipient.email],
                reply_to=('reply.tome@foo.bar',)
            )
            email_sender.queue(message)
        try:
            num_sent = email_sender.send_all()
        except Exception:
            logger.exception(
                f"Failed to send notification emails with subject [{subject}]."
            )
            num_sent = 0
        return num_sent == len(recipients)


class ActionModeratorApprovalTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events"""
    notification = 'submitted'


class ActionModeratorCancelTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events"""
    notification = 'cancelled'
