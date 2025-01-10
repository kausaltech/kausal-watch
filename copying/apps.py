from __future__ import annotations

from django.apps import AppConfig


class CopyingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "copying"
