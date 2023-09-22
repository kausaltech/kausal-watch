import logging
from anymail.signals import pre_send, post_send
from django.db.models.signals import post_save
from django.dispatch import receiver
from wagtail.signals import task_submitted

from .mail import ActionModeratorApprovalTaskStateSubmissionEmailNotifier
from .models import Plan, PlanFeatures
from notifications.models import NotificationSettings

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
            f"email with subject '{message.subject}' to recipient {email}"
        )


action_moderator_approval_task_submission_email_notifier = ActionModeratorApprovalTaskStateSubmissionEmailNotifier()


def register_signal_handlers():
    task_submitted.connect(
        action_moderator_approval_task_submission_email_notifier,
        dispatch_uid='action_moderator_approval_task_submitted_email_notification',
    )
