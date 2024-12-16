import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from wagtail.signals import task_cancelled, task_submitted, workflow_approved

from anymail.signals import post_send, pre_send

from indicators.models import Indicator, IndicatorContactPerson
from notifications.models import NotificationSettings
from orgs.models import Organization, OrganizationPlanAdmin
from people.models import Person

from .mail import (
    ActionModeratorApprovalTaskStateSubmissionEmailNotifier,
    ActionModeratorCancelTaskStateSubmissionEmailNotifier,
    WorkflowStateApprovalWithCommentEmailNotifier,
)
from .models import Action, ActionContactPerson, ActionResponsibleParty, Category, GeneralPlanAdmin, Plan, PlanFeatures
from .models.attributes import AttributeType
from .perms import get_people_with_login_rights

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Plan)
def create_notification_settings(sender, instance, created, **kwargs):
    if created:
        NotificationSettings.objects.create(plan=instance)


@receiver(post_save, sender=Plan)
def create_plan_features(sender, instance, created, **kwargs):
    if created:
        PlanFeatures.objects.create(plan=instance)


@receiver(pre_send)
def log_email_before_sending(sender, message, esp_name, **kwargs):
    logger.info(f"Sending email with subject '{message.subject}' via {esp_name} to recipients {message.to}")


@receiver(post_send)
def log_email_send_status(sender, message, status, esp_name, **kwargs):
    for email, recipient_status in status.recipients.items():
        logger.info(
            f"Email send status '{recipient_status.status}' (message ID {recipient_status.message_id}) from {esp_name} for "
            f"email with subject '{message.subject}' to recipient {email}",
        )


@receiver(post_save, sender=AttributeType)
@receiver(post_delete, sender=AttributeType)
def invalidate_attribute_type_cache(sender, instance, **kwargs):
    # Attribute type cache may get stale when creating, editing or deleting attribute types
    Action.get_attribute_types_for_plan.cache_clear()
    Category.get_attribute_types_for_plan.cache_clear()


action_moderator_approval_task_submission_email_notifier = ActionModeratorApprovalTaskStateSubmissionEmailNotifier()
action_moderator_cancel_task_submission_email_notifier = ActionModeratorCancelTaskStateSubmissionEmailNotifier()
workflow_approval_email_notifier = WorkflowStateApprovalWithCommentEmailNotifier()

MODELS_WHICH_AFFECT_LOGIN_RIGHTS = (
    Person,
    GeneralPlanAdmin,
    ActionContactPerson,
    IndicatorContactPerson,
    ActionResponsibleParty,
    Action,
    Indicator,
    OrganizationPlanAdmin,
    Organization,
)


def clear_login_rights_cache(sender, instance, **kwargs):
    get_people_with_login_rights.cache_clear()


for model in MODELS_WHICH_AFFECT_LOGIN_RIGHTS:
    post_save.connect(clear_login_rights_cache, sender=model)
    post_delete.connect(clear_login_rights_cache, sender=model)


def register_signal_handlers():
    task_submitted.connect(
        action_moderator_approval_task_submission_email_notifier,
        dispatch_uid='action_moderator_approval_task_submitted_email_notification',
    )
    task_cancelled.connect(
        action_moderator_cancel_task_submission_email_notifier,
        dispatch_uid='action_moderator_cancel_task_submitted_email_notification',
    )
    workflow_approved.connect(
        workflow_approval_email_notifier,
        dispatch_uid="workflow_state_approved_email_notification",
    )
