import typing

from .models import NotificationType
from actions.models import Plan, ActionTask, Action
from feedback.models import UserFeedback
from indicators.models import Indicator
from people.models import Person

MINIMUM_NOTIFICATION_PERIOD = 5  # days


class Notification:
    type: NotificationType
    plan: Plan
    obj: typing.Union[Action, ActionTask, Indicator, UserFeedback]

    def __init__(self, type: NotificationType, plan: Plan, obj):
        self.type = type
        self.plan = plan
        self.obj = obj

    def _get_type(self):
        return self.type.identifier

    def get_context(self):
        # Implement in subclass
        raise NotImplementedError()

    def mark_sent(self, person: Person, now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        self.obj.sent_notifications.create(sent_at=now, person=person, type=self._get_type())

    def notification_last_sent(self, person: Person = None, now=None) -> typing.Optional[int]:
        if now is None:
            now = self.plan.now_in_local_timezone()
        notifications = self.obj.sent_notifications.filter(type=self._get_type())
        if person:
            notifications = notifications.filter(person=person)
        last_notification = notifications.order_by('-sent_at').first()
        if not last_notification:
            return None
        else:
            return (now - last_notification.sent_at).days

    def _queue_notification(self, person: Person):
        person._notifications.setdefault(self._get_type(), []).append(self)


class DeadlinePassedNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_late: int):
        super().__init__(type, plan, obj)
        self.days_late = days_late

    def generate_notifications(self, contacts: typing.List[Person], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for person in contacts:
            days = self.notification_last_sent(person, now=now)
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

            self._queue_notification(person)


class TaskLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_late: int):
        super().__init__(NotificationType.TASK_LATE, plan, task, days_late)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_late=self.days_late)


class UpdatedIndicatorValuesLateNotification(DeadlinePassedNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_late: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_LATE, plan, indicator, days_late)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_late=self.days_late)


class DeadlineSoonNotification(Notification):
    def __init__(self, type: NotificationType, plan: Plan, obj, days_left: int):
        super().__init__(type, plan, obj)
        self.days_left = days_left

    def generate_notifications(self, contacts: typing.List[Person], now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        for person in contacts:
            days = self.notification_last_sent(person, now=now)
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

            self._queue_notification(person)


class TaskDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, task: ActionTask, days_left: int):
        super().__init__(NotificationType.TASK_DUE_SOON, plan, task, days_left)

    def get_context(self):
        return dict(task=self.obj.get_notification_context(self.plan), days_left=self.days_left)


class UpdatedIndicatorValuesDueSoonNotification(DeadlineSoonNotification):
    def __init__(self, plan: Plan, indicator: Indicator, days_left: int):
        super().__init__(NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON, plan, indicator, days_left)

    def get_context(self):
        return dict(indicator=self.obj.get_notification_context(self.plan), days_left=self.days_left)


class NotEnoughTasksNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.NOT_ENOUGH_TASKS, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan))

    def generate_notifications(self, now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        contacts = self.obj._notification_recipients
        for person in contacts:
            days_since = self.notification_last_sent(person, now=now)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class ActionNotUpdatedNotification(Notification):
    def __init__(self, plan: Plan, action: Action):
        super().__init__(NotificationType.ACTION_NOT_UPDATED, plan, action)

    def get_context(self):
        return dict(action=self.obj.get_notification_context(self.plan), last_updated_at=self.obj.updated_at)

    def generate_notifications(self, now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        contacts = self.obj._notification_recipients
        for person in contacts:
            days_since = self.notification_last_sent(person, now=now)
            if days_since is not None:
                if days_since < 30:
                    # We don't want to remind too often
                    continue

            self._queue_notification(person)


class UserFeedbackReceivedNotification(Notification):
    def __init__(self, plan: Plan, user_feedback: UserFeedback):
        super().__init__(NotificationType.USER_FEEDBACK_RECEIVED, plan, user_feedback)

    def get_context(self):
        return {'user_feedback': self.obj}

    def generate_notifications(self, now=None):
        if now is None:
            now = self.plan.now_in_local_timezone()
        # Send user feedback received notifications only if they haven't been sent yet to anybody
        if self.notification_last_sent(now=now) is None:
            for person in self.obj._notification_recipients:
                self._queue_notification(person)
