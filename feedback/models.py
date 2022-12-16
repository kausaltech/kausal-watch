from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from actions.models import Plan


class UserFeedback(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='user_feedbacks')
    name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    comment = models.TextField()

    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='user_feedbacks')

    class Meta:
        verbose_name = _('user feedback')
        verbose_name_plural = _('user feedbacks')

    def user_can_change_is_processed(self, user):
        return user.is_general_admin_for_plan(self.plan)

    def __str__(self):
        sender = self.name or self.email
        return f'{sender} ({self.created_at})'
