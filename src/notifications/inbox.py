from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType

from notifications.models import InboxNotification

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import Model

    from actions.models import Plan
    from users.models import User


def notify(
    recipients: Iterable[User],
    type: InboxNotification.Type,
    obj: Model,
    *,
    plan: Plan | None = None,
    actor: User | None = None,
    comment: str = '',
) -> list[InboxNotification]:
    content_type = ContentType.objects.get_for_model(obj)
    unique_recipients = {user.pk: user for user in recipients if actor is None or user.pk != actor.pk}
    return InboxNotification.objects.bulk_create(
        InboxNotification(
            recipient=user,
            plan=plan,
            type=type,
            content_type=content_type,
            object_id=str(obj.pk),
            object_title=str(obj)[:1000],
            actor=actor,
            comment=comment,
        )
        for user in unique_recipients.values()
    )
