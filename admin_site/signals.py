import logging
from django.dispatch import receiver
from django.contrib import messages
from hijack.signals import hijack_started, hijack_ended
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

@receiver(hijack_started)
def on_hijack_started(sender, hijacker, hijacked, request, **kwargs):
    logger.info(f"{hijacker} has started impersonation for user {hijacked}")
    messages.warning(request, _(f"You are now viewing the site as {hijacked}"))

@receiver(hijack_ended)
def on_hijack_ended(sender, hijacker, hijacked, request, **kwargs):
    logger.info(f"{hijacker} has ended impersonation for user {hijacked}")
    messages.success(request, _(f"You have stopped viewing the site as {hijacked} and have returned to your original account."))
