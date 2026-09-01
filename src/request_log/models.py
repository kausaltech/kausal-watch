from __future__ import annotations

from django.db import models

from kausal_common.logging.request_log.models import BaseLoggedRequest

from users.models import User


class LoggedRequest(BaseLoggedRequest):
    impersonator: models.ForeignKey[User | None, User | None] = models.ForeignKey(  # pyright: ignore
        User, blank=True, null=True, on_delete=models.SET_NULL, related_name='logged_impersonated_requests'
    )
