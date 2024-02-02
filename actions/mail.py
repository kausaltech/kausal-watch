from wagtail.admin.mail import EmailNotificationMixin, Notifier
from wagtail.models import TaskState

from .models import Action, ActionContactPerson
from users.models import User


class BaseActionModeratorApprovalTaskStateEmailNotifier(EmailNotificationMixin, Notifier):
    """A base notifier to send updates for UserApprovalTask events"""

    def __init__(self):
        # Allow TaskState to send notifications
        super().__init__((TaskState,))

    def get_context(self, task_state, **kwargs):
        context = super().get_context(task_state, **kwargs)
        context['object'] = task_state.workflow_state.content_object
        context['task'] = task_state.task.specific
        context["model_name"] = context["object"]._meta.verbose_name
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


class ActionModeratorApprovalTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events"""
    notification = 'submitted'


class ActionModeratorCancelTaskStateSubmissionEmailNotifier(BaseActionModeratorApprovalTaskStateEmailNotifier):
    """A notifier to send updates for ActionModeratorApprovalTask submission events"""
    notification = 'cancelled'
