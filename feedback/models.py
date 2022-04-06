from django.db import models
from django.utils.translation import gettext_lazy as _

from actions.models import Plan


class UserFeedback(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    comment = models.TextField()

    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('user feedback')
        verbose_name_plural = _('user feedbacks')

    def __str__(self):
        return str(self.created_at)
