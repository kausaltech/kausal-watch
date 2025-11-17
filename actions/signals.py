import logging

from django.db.models.signals import post_delete, post_migrate, post_save
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
from .perms import get_people_with_login_rights, sync_all_group_permissions_for_plan

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Plan)
def create_notification_settings(sender, instance, created, **kwargs):
    if created:
        NotificationSettings.objects.create(plan=instance)


@receiver(post_save, sender=Plan)
def create_plan_features_and_sync_group_permissions(sender, instance, created, **kwargs):
    if created:
        PlanFeatures.objects.create(plan=instance)
        return
    # post_save is called twice for Plans
    # since super() is called twice in Plan.save.
    # During the first call the admin_group and such
    # are not saved yet. Make sure created is false
    # before the following call:
    sync_all_group_permissions_for_plan(instance)


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

@receiver(post_delete, sender=ActionContactPerson)
def fix_deleted_contact_person_in_draft(sender, instance, **kwargs):
    # When deleting an ActionContactPerson, drafts of that action may reference the deleted instance, which causes an
    # error when trying to publish the action. Here we remove the reference from the revision content so that, when the
    # draft is published, the ActionContactPerson is created anew instead of trying (and failing) to change the one that
    # doesn't exist anymore.
    # TODO: This may need to be done for other models as well; investigate.
    assert isinstance(instance, ActionContactPerson)
    instance.fix_action_draft_after_deletion()


@receiver(post_delete, sender=ActionResponsibleParty)
def fix_deleted_responsible_party_in_draft(sender, instance, **kwargs):
    # When deleting an ActionResponsibleParty, drafts of that action may reference the deleted instance, which causes an
    # error when trying to publish the action. Here we remove the reference from the revision content so that, when the
    # draft is published, the ActionResponsibleParty is created anew instead of trying (and failing) to change the one
    # that doesn't exist anymore.
    # TODO: This may need to be done for other models as well; investigate.
    assert isinstance(instance, ActionResponsibleParty)
    instance.fix_action_draft_after_deletion()


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


def sync_permissions(sender, **kwargs):
    from actions.perms import sync_group_permissions
    if sender.label != 'actions':
        return
    print('Syncing permissions')
    sync_group_permissions()


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
    post_migrate.connect(sync_permissions, dispatch_uid='sync_app_permissions')
