from __future__ import annotations
from abc import ABC, abstractmethod
import datetime
from enum import Enum
import typing

from django.db.models import Q
from django.utils.translation import pgettext, gettext_lazy as _
from markupsafe import Markup

from actions.models import Plan, ActionTask, Action
from feedback.models import UserFeedback
from indicators.models import Indicator

if typing.TYPE_CHECKING:
    from . import NotificationObject
    from .engine import NotificationEngine
    from .recipients import NotificationRecipient
    from .models import ManuallyScheduledNotificationTemplate
    from django_stubs_ext import StrPromise

MINIMUM_NOTIFICATION_PERIOD = 5  # days


class Notification(ABC):
    type: NotificationType
    plan: Plan
    obj: NotificationObject

    def __init__(self, type: NotificationType, plan: Plan, obj: typing.Any):
        self.type = type
        self.plan = plan
        self.obj = obj

    def get_context(self):
        # Implement in subclass
        raise NotImplementedError()

    def mark_sent(self, recipient: NotificationRecipient, now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        recipient.create_sent_notification(self.obj, sent_at=now, type=self.type.identifier)

    def notification_last_sent_datetime(self, recipient: NotificationRecipient | None = None) -> datetime.datetime | None:
        notifications = self.obj.sent_notifications.filter(type=self.type.identifier)
        if recipient:
            notifications = notifications.recipient(recipient)
        last_notification = notifications.order_by('-sent_at').first()
        if last_notification is None:
            return None
        return last_notification.sent_at

    def days_since_notification_last_sent(self, recipient: NotificationRecipient | None = None, now=None) -> int | None:
        last_notification_sent_at = self.notification_last_sent_datetime(recipient)
        if last_notification_sent_at is None:
            return None
        if now is None:
            now = self.plan.now_in_local_timezone()
        return (now - last_notification_sent_at).days

    def get_content_blocks(self, base_template, template) -> dict[str, Markup]:
        cb_qs = base_template.content_blocks.filter(Q(template__isnull=True) | Q(template=template))
        return {cb.identifier: Markup(cb.content) for cb in cb_qs}

    def get_identifier(self) -> str | None:
        return None

    @classmethod
    @abstractmethod
    def get_default_intro_text(cls) -> str | None:
        '''Return None if this notification type does not need a default text
        when initializing the default notification templates, otherwise a string'''
        pass

    @classmethod
    @abstractmethod
    def get_verbose_name(cls) -> StrPromise:
        pass


class DeadlinePassedNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_late: int):
        super().__init__(type, plan, obj)
        self.days_late = days_late

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for recipient in recipients:
            days = self.days_since_notification_last_sent(recipient, now=now)
            if days is not None:
                if days < MINIMUM_NOTIFICATION_PERIOD:
                    # We don't want to remind too often
                    continue
                if self.days_late not in (1, 7) and not (self.days_late % 30 == 0):
                    # If we have reminded about this before, let's only
                    # send a reminder if it's late one day, a week or 30, 60, 90... days
                    continue
            else:
                # If we have never reminded about this, send a notification
                # no matter how many days are left.
                pass

            engine.queue_notification(self, recipient)


class TaskLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_late: int):
        super().__init__(NotificationType.TASK_LATE, plan, task, days_late)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_late=self.days_late)

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'task_late',
            "This is an automatic reminder about updating "
            "the task information of your action in the action plan. "
            "There is an action whose deadline has passed. The action "
            "is shown to be late until you mark it as done and fill in "
            "some details."
        )

    @classmethod
    def get_verbose_name(cls):
        return _("Task is late")


class UpdatedIndicatorValuesLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_late: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_LATE, plan, indicator, days_late)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_late=self.days_late)

    @classmethod
    def get_verbose_name(cls):
        return _("Updated indicator values are late")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'updated_indicator_values_late',
            "This is an automatic "
            "reminder about updating indicator details in the action "
            "plan.  The deadline for updating the indicator values has "
            "passed. Please go and update the indicator with the latest "
            "values."
        )

class DeadlineSoonNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_left: int):
        super().__init__(type, plan, obj)
        self.days_left = days_left

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for recipient in recipients:
            days = self.days_since_notification_last_sent(recipient, now=now)
            if days is not None:
                if days < MINIMUM_NOTIFICATION_PERIOD:
                    # We don't want to remind too often
                    continue
                if self.days_left not in (1, 7, 30):
                    # If we have reminded about this before, let's only
                    # send a reminder if it's tomorrow, in a week or in a month
                    continue
            else:
                # If we have never reminded about this, send a notification
                # no matter how many days are left.
                pass

            engine.queue_notification(self, recipient)


class TaskDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_left: int):
        super().__init__(NotificationType.TASK_DUE_SOON, plan, task, days_left)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_left=self.days_left)

    @classmethod
    def get_verbose_name(cls):
        return _("Task is due soon")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'task_due_soon',
            "This is an automatic reminder about "
            "updating the task information of your action in the action "
            "plan.  There is an action in the action plan with a "
            "deadline approaching. Please remember to mark the task as "
            "done as soon as it has been completed. After the deadline "
            "has gone, the action will be marked as late. You can edit "
            "the task details from the link below."
        )


class UpdatedIndicatorValuesDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_left: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON, plan, indicator, days_left)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_left=self.days_left)

    @classmethod
    def get_verbose_name(cls):
        return _("Updated indicator values are due soon")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'updated_indicator_values_due_soon',
            "This is an automatic "
            "reminder about updating indicator details in the action "
            "plan.  The deadline for updating the indicator values is "
            "approaching. Please go and update the indicator with the "
            "latest values."
        )


class NotEnoughTasksNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.NOT_ENOUGH_TASKS, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan))

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for recipient in recipients:
            days_since = self.days_since_notification_last_sent(recipient, now=now)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            engine.queue_notification(self, recipient)

    @classmethod
    def get_verbose_name(cls) -> StrPromise:
        return _("Action doesn't have enough in-progress tasks")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'not_enough_tasks',
            "This is an automatic reminder about "
            "updating the action details in the action plan.  You can "
            "see on the action plan watch site what has already been "
            "done to further the actions and what has been planned for "
            "the future.  This means that it would be preferrable for "
            "each action to have at least one upcoming task within the "
            "next year. Please go and add tasks for the action which "
            "show what the next planned steps for the action are."
        )


class ActionNotUpdatedNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.ACTION_NOT_UPDATED, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan), last_updated_at=self.obj.updated_at)

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for recipient in recipients:
            days_since = self.days_since_notification_last_sent(recipient, now=now)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            engine.queue_notification(self, recipient)

    @classmethod
    def get_verbose_name(cls):
        return _("Action metadata has not been updated recently")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'action_not_updated',
            "This is an automatic reminder about "
            "updating the action details in the action plan.  You can "
            "see on the action plan watch site what has already been done "
            "to further the actions and what has been planned for the "
            "future.  It's already six months since you last updated an "
            "action. Please go and update the action with the latest "
            "information. You can add an upcoming task to the action at "
            "the same time."
        )


class UserFeedbackReceivedNotification(Notification):
    def __init__(self, plan: Plan, user_feedback: UserFeedback):
        super().__init__(NotificationType.USER_FEEDBACK_RECEIVED, plan, user_feedback)

    def get_context(self):
        return {'user_feedback': self.obj}

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        # Send user feedback received notifications only if they haven't been sent yet to anybody
        if self.days_since_notification_last_sent(now=now) is None:
            for recipient in recipients:
                engine.queue_notification(self, recipient)

    @classmethod
    def get_verbose_name(cls):
        return _("User feedback received")

    @classmethod
    def get_default_intro_text(cls):
        return pgettext(
            'user_feedback_received',
            "A user has submitted feedback."
        )


class ManuallyScheduledNotification(Notification):
    def __init__(self, plan: Plan, template: ManuallyScheduledNotificationTemplate):
        super().__init__(NotificationType.MANUALLY_SCHEDULED, plan, template)

    def get_context(self):
        return {'content': self.obj.content}

    def generate_notifications(self, engine: NotificationEngine, recipients: typing.Sequence[NotificationRecipient], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        trigger_datetime = datetime.datetime.combine(
            self.obj.date, datetime.datetime.min.time()
        ).replace(tzinfo=self.plan.tzinfo)

        last_sent = self.notification_last_sent_datetime()
        if last_sent is None:
            notification_has_been_rescheduled = False
        else:
            notification_has_been_rescheduled = trigger_datetime > last_sent

        if now < trigger_datetime:
            return
        if last_sent is not None and not notification_has_been_rescheduled:
            # The notification has already been sent
            return
        for recipient in recipients:
            engine.queue_notification(self, recipient)

    def get_identifier(self) -> str | None:
        return f'{self.obj.date.isoformat()}-{self.obj.subject}'

    def get_content_blocks(self, base_template, template) -> dict[str, Markup]:
        cb_qs = base_template.content_blocks.filter(template__isnull=True)
        result = {cb.identifier: Markup(cb.content) for cb in cb_qs}
        result['intro'] = template.content
        return result

    @classmethod
    def get_verbose_name(cls):
        return _("Manually scheduled notification")

    @classmethod
    def get_default_intro_text(cls):
        return None

    def __str__(self):
        return f'ManuallyScheduledNotification(date={self.obj.date.isoformat()}, subject="{self.obj.subject}")'


class NotificationType(Enum):
    TASK_LATE = TaskLateNotification
    TASK_DUE_SOON = TaskDueSoonNotification
    ACTION_NOT_UPDATED = ActionNotUpdatedNotification
    NOT_ENOUGH_TASKS = NotEnoughTasksNotification
    UPDATED_INDICATOR_VALUES_LATE = UpdatedIndicatorValuesLateNotification
    UPDATED_INDICATOR_VALUES_DUE_SOON = UpdatedIndicatorValuesDueSoonNotification
    USER_FEEDBACK_RECEIVED = UserFeedbackReceivedNotification
    MANUALLY_SCHEDULED = ManuallyScheduledNotification

    @property
    def identifier(self):
        return self.name.lower()

    @property
    def default_intro_text(self):
        return self.value.get_default_intro_text()

    @property
    def verbose_name(self):
        return self.value.get_verbose_name()
