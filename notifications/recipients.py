from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from django.db import models
from typing import Any, Dict, Optional

from .notifications import Notification
from .queue import NotificationQueueItem
from people.models import Person

if typing.TYPE_CHECKING:
    from . import NotificationObject
    from .models import SentNotification
    from admin_site.models import Client


class NotificationRecipient(ABC):
    @abstractmethod
    def filter_sent_notifications(self, qs: models.QuerySet):
        pass

    @abstractmethod
    def create_sent_notification(self, obj: NotificationObject, **kwargs) -> SentNotification:
        """Create a SentNotification concerning the given object, which must have an attribute `sent_notifications`."""
        pass

    @abstractmethod
    def get_notification_context(self) -> Dict[str, Any]:
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

    def create_sent_notification(self, obj, **kwargs) -> SentNotification:
        assert 'person' not in kwargs
        return obj.sent_notifications.create(person=self.person, **kwargs)

    def get_notification_context(self) -> Dict[str, Any]:
        return self.person.get_notification_context()

    def get_email(self) -> Optional[str]:
        return self.person.email


@dataclass(frozen=True)  # frozen to make it hashable
class EmailRecipient(NotificationRecipient):
    email: str
    client: Client  # Used for obtaining the admin URL etc.

    def filter_sent_notifications(self, qs: models.QuerySet):
        return qs.filter(email=self.email)

    def create_sent_notification(self, obj, **kwargs) -> SentNotification:
        assert 'email' not in kwargs
        return obj.sent_notifications.create(email=self.email, **kwargs)

    def get_notification_context(self) -> Dict[str, Any]:
        context = {
            'admin_url': self.client.get_admin_url(),
        }
        logo_context = self.client.get_notification_logo_context()
        if logo_context:
            context['logo'] = logo_context
        return context

    def get_email(self) -> Optional[str]:
        return self.email
