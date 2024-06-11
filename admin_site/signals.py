from django.dispatch import receiver
from django.contrib import messages
from hijack.signals import hijack_started, hijack_ended # type: ignore[import-untyped]
from django.utils.translation import gettext as _
from loguru import logger

from users.models import User
from aplans.types import WatchAdminRequest

hijack_log = logger.bind(impersonation=True)

@receiver(hijack_started)
def on_hijack_started(sender, hijacker: User, hijacked: User, request: WatchAdminRequest, **kwargs):
    hijack_log.bind(impersonation_actor=hijacker.email, impersonation_target=hijacked.email).info(
        f"{hijacker} has started impersonation for user {hijacked}")
    messages.warning(request, _(f"You are now viewing the site as {hijacked}"))

@receiver(hijack_ended)
def on_hijack_ended(sender, hijacker: User, hijacked: User, request: WatchAdminRequest, **kwargs):
    hijack_log.bind(impersonation_actor=hijacker.email, impersonation_target=hijacked.email).info(
        f"{hijacker} has ended impersonation for user {hijacked}")
    messages.success(request, _(f"You have stopped viewing the site as {hijacked} and have returned to your original account."))
