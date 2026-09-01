import logging
from contextlib import suppress
from typing import Any

from django.db.models.signals import m2m_changed, post_delete, post_migrate, post_save, pre_save
from django.dispatch import receiver
from wagtail.signals import task_cancelled, task_submitted, workflow_approved

from anymail.signals import post_send, pre_send

from indicators.models import Indicator, IndicatorContactPerson
from notifications.models import NotificationSettings
from orgs.models import Organization, OrganizationPlanAdmin
from people.models import Person
from users.models import User
from users.perms import create_permissions

from .mail import (
    ActionModeratorApprovalTaskStateSubmissionEmailNotifier,
    ActionModeratorCancelTaskStateSubmissionEmailNotifier,
    WorkflowStateApprovalWithCommentEmailNotifier,
)
from .models import Action, ActionContactPerson, ActionResponsibleParty, GeneralPlanAdmin, Plan, PlanFeatures
from .perms import get_people_with_login_rights, sync_all_group_permissions_for_plan, sync_group_permissions

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


MODELS_WHICH_AFFECT_USER_GROUPS = (
    GeneralPlanAdmin,
    ActionContactPerson,
    IndicatorContactPerson,
)


def _sync_user_groups_for_person_ids(person_ids: set[int]) -> None:
    for person in Person.objects.filter(pk__in=person_ids).select_related('user'):
        user = person.get_corresponding_user()
        if user is None:
            continue
        with suppress(User.DoesNotExist):
            create_permissions(User.objects.get(pk=user.pk))


def remember_old_permission_person(
    sender: Any,
    instance: GeneralPlanAdmin | ActionContactPerson | IndicatorContactPerson,
    **kwargs: object,
) -> None:
    if instance.pk is None:
        return

    # Intentionally get the old value of person_id from the database
    old_person_id = sender.objects.filter(pk=instance.pk).values_list('person_id', flat=True).first()
    permission_instance: Any = instance
    permission_instance._old_person_id = old_person_id


def sync_permission_user_groups(
    sender: type[object],
    instance: GeneralPlanAdmin | ActionContactPerson | IndicatorContactPerson,
    **kwargs: object,
) -> None:
    person_ids = {instance.person_id}
    old_person_id = getattr(instance, '_old_person_id', None)
    if isinstance(old_person_id, int):
        person_ids.add(old_person_id)
    _sync_user_groups_for_person_ids(person_ids)


def sync_deleted_person_user_groups(sender: type[Person], instance: Person, **kwargs: object) -> None:
    user = instance.get_corresponding_user()
    if user is None:
        return

    with suppress(User.DoesNotExist):
        create_permissions(User.objects.get(pk=user.pk))


for model in MODELS_WHICH_AFFECT_USER_GROUPS:
    pre_save.connect(remember_old_permission_person, sender=model)
    post_save.connect(sync_permission_user_groups, sender=model)
    post_delete.connect(sync_permission_user_groups, sender=model)


def sync_general_admin_m2m_user_groups(
    sender: GeneralPlanAdmin,
    instance: Plan | Person,
    action: str,
    reverse: bool,
    model: Person | Plan,
    pk_set: set[int] | None,
    **kwargs: dict[str, Any],
) -> None:
    if action not in {'post_add', 'post_remove', 'pre_clear', 'post_clear'}:
        return

    if isinstance(instance, Person):
        assert reverse
        assert model == Plan
        if instance.pk is None:
            return
        _sync_user_groups_for_person_ids({instance.pk})
        return

    assert not reverse
    assert model == Person

    plan: Plan = instance
    if action == 'pre_clear':
        plan._cleared_general_admin_person_ids = set(plan.general_admins.values_list('pk', flat=True))
        return
    if action == 'post_clear':
        person_ids: set[int] = getattr(plan, '_cleared_general_admin_person_ids', set())
    elif pk_set is None:
        return
    else:
        person_ids = set(pk_set)
    _sync_user_groups_for_person_ids(person_ids)


m2m_changed.connect(sync_general_admin_m2m_user_groups, sender=Plan.general_admins.through)
post_delete.connect(sync_deleted_person_user_groups, sender=Person)


def sync_permissions(sender, **kwargs):
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
        dispatch_uid='workflow_state_approved_email_notification',
    )
    post_migrate.connect(sync_permissions, dispatch_uid='sync_app_permissions')
