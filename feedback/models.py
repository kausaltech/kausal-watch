from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from actions.models import Action, Plan


class UserFeedback(models.Model):
    class FeedbackType(models.TextChoices):
        GENERAL = '', _('General')
        ACCESSIBILITY = 'accessibility', _('Accessibility')
        ACTION = 'action', _('Action')

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='user_feedbacks', verbose_name=_("plan"))
    type = models.CharField(
        max_length=30, choices=FeedbackType.choices, verbose_name=_("type"), blank=True,
    )
    action = models.ForeignKey(
        Action, blank=True, null=True, on_delete=models.SET_NULL, related_name='user_feedbacks',
        verbose_name=_("action"),
    )

    name = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("name"))
    email = models.EmailField(null=True, blank=True, verbose_name=_("email address"))
    comment = models.TextField(verbose_name=_("comment"))

    url = models.URLField(verbose_name=_("URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("created at"))
    is_processed = models.BooleanField(default=False, verbose_name=_("is processed"))

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='user_feedbacks')

    class Meta:
        verbose_name = _('user feedback')
        verbose_name_plural = _('user feedbacks')

    def user_can_change_is_processed(self, user):
        return user.is_general_admin_for_plan(self.plan)

    def __str__(self):
        sender = self.name or self.email
        return f'{sender} ({self.created_at})'
