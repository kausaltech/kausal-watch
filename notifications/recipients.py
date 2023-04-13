from abc import ABC, abstractmethod
from dataclasses import dataclass
from django.db import models
from typing import Optional

from .notifications import Notification
from .queue import NotificationQueueItem
from people.models import Person


class NotificationRecipient(ABC):
    @abstractmethod
    def filter_sent_notifications(self, qs: models.QuerySet):
        pass

    @abstractmethod
    def create_sent_notification(self, **kwargs):
        pass

    @abstractmethod
    def get_notification_context(self):
        pass

    def queue_item(self, notification: Notification) -> NotificationQueueItem:
        return NotificationQueueItem(notification=notification, recipient=self)

    def get_email(self) -> Optional[str]:
        """If this recipient has a corresponding email address, return it, else return None."""
        return None


@dataclass(frozen=True)  # frozen to make it hashable
class PersonRecipient(NotificationRecipient):
    person: Person

    def filter_sent_notifications(self, qs: models.QuerySet):
        return qs.filter(person=self.person)

    def create_sent_notification(self, **kwargs):
        from .models import SentNotification
        assert 'person' not in kwargs
        return SentNotification.objects.create(person=self.person, **kwargs)

    def get_notification_context(self):
        return self.person.get_notification_context()

    def get_email(self) -> Optional[str]:
        return self.person.email


@dataclass(frozen=True)  # frozen to make it hashable
class EmailRecipient(NotificationRecipient):
    email: str

    def filter_sent_notifications(self, qs: models.QuerySet):
        return qs.filter(email=self.email)

    def create_sent_notification(self, **kwargs):
        from .models import SentNotification
        assert 'email' not in kwargs
        return SentNotification.objects.create(email=self.email, **kwargs)

    # TODO
    # def get_notification_context(self):
    #     pass

    def get_email(self) -> Optional[str]:
        return self.email
