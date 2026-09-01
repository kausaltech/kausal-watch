from typing import TYPE_CHECKING

from django.contrib import messages
from django.dispatch import receiver
from django.utils.translation import gettext as _

from hijack.signals import hijack_ended, hijack_started  # type: ignore[import-untyped]
from loguru import logger

if TYPE_CHECKING:
    from aplans.types import WatchAdminRequest

    from users.models import User

hijack_log = logger.bind(impersonation=True)


@receiver(hijack_started)
def on_hijack_started(sender, hijacker: User, hijacked: User, request: WatchAdminRequest, **kwargs):
    hijack_log.bind(impersonation_actor=hijacker.email, impersonation_target=hijacked.email).info(
        f'{hijacker} has started impersonation for user {hijacked}'
    )
    messages.warning(request, _('You are now viewing the site as %(user)s.') % {'user': hijacked})


@receiver(hijack_ended)
def on_hijack_ended(sender, hijacker: User, hijacked: User, request: WatchAdminRequest, **kwargs):
    hijack_log.bind(impersonation_actor=hijacker.email, impersonation_target=hijacked.email).info(
        f'{hijacker} has ended impersonation for user {hijacked}'
    )
    message = _('You have stopped viewing the site as %(user)s and have returned to your original account.') % {
        'user': hijacked,
    }
    messages.success(request, message)
