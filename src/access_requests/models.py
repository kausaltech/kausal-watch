from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import OuterRef, Q, Subquery
from django.utils.translation import gettext_lazy as _

from kausal_common.models.types import ModelManager

if TYPE_CHECKING:
    from datetime import datetime

    from kausal_common.models.types import FK

    from actions.models import Plan
    from people.models import Person
    from users.models import User


class AccessRequestQuerySet(models.QuerySet['AccessRequest']):
    def pending(self) -> AccessRequestQuerySet:
        """Return the pending requests, oldest first, so those who have waited longest come first."""
        return self.filter(status=AccessRequest.Status.PENDING).order_by('created_at', 'pk')

    def with_previous_rejection(self) -> AccessRequestQuerySet:
        """Annotate `previously_rejected_at`: when an earlier request of the same address to the same plan was rejected."""
        earlier_rejections = AccessRequest.objects.filter(
            plan=OuterRef('plan'),
            email=OuterRef('email'),
            status=AccessRequest.Status.REJECTED,
            created_at__lt=OuterRef('created_at'),
        ).order_by('-decided_at')
        return self.annotate(previously_rejected_at=Subquery(earlier_rejections.values('decided_at')[:1]))


if TYPE_CHECKING:

    class AccessRequestManager(ModelManager['AccessRequest', AccessRequestQuerySet]):
        pass

else:
    AccessRequestManager = ModelManager.from_queryset(AccessRequestQuerySet)


class AccessRequest(models.Model):
    """
    A visitor's request to read an internal plan's public site.

    Each attempt is its own row: a visitor who was rejected and asks again gets a new request, so
    the rejection stays on record and the new one can be shown as "requested again".
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')

    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='access_requests', verbose_name=_('plan')
    )
    email = models.EmailField(verbose_name=_('email address'))
    first_name = models.CharField(max_length=100, blank=True, verbose_name=_('first name'))
    last_name = models.CharField(max_length=100, blank=True, verbose_name=_('last name'))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name=_('status'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name=_('decided at'))
    decided_by: FK[User | None] = models.ForeignKey(
        'users.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name=_('decided by')
    )
    person: FK[Person | None] = models.ForeignKey(
        'people.Person',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='access_requests',
        verbose_name=_('person'),
    )

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='access_requests')

    objects: ClassVar[AccessRequestManager] = AccessRequestManager()

    # Set by `AccessRequestQuerySet.with_previous_rejection()`.
    previously_rejected_at: datetime | None

    class Meta:
        verbose_name = _('access request')
        verbose_name_plural = _('access requests')
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'email'],
                condition=Q(status='pending'),
                name='access_request_one_pending_per_email',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.email} ({self.get_status_display()})'
