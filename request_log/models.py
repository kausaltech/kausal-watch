from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone

from users.models import User


class LoggedRequest(models.Model):
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=2000)
    raw_request = models.TextField()
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name='logged_requests')
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    impersonator = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, related_name='logged_impersonated_requests')
    class Meta:
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        date_cutoff = timezone.now() - timedelta(days=settings.REQUEST_LOG_MAX_DAYS)
        LoggedRequest.objects.filter(created_at__lt=date_cutoff).delete()
        return result

    def __str__(self):
        result = f'{self.method} {self.path}'
        if self.user:
            result += f' from {self.user}'
        return result
