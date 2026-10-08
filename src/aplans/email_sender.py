from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.conf import settings
from django.core.mail import get_connection

if TYPE_CHECKING:
    from types import TracebackType

    from django.core.mail import EmailMessage
    from django.core.mail.backends.base import BaseEmailBackend

    from actions.models import Plan


class EmailSender:
    """
    Send emails with the plan's From and Reply-To headers.

    Either queue messages and call `send_all()`, or use the sender as a context manager and
    `send()` each message as it is ready; the messages then share one connection, opened on
    the first `send()`.
    """

    messages: list[EmailMessage]
    from_email: str | None
    reply_to: list | None
    connection: BaseEmailBackend | None

    def __init__(self, plan: Plan | None = None):
        self.messages = []
        self.connection = None
        if plan is None:
            self.from_email = None
            self.reply_to = None
        base_template = getattr(plan, 'notification_base_template', None)
        if base_template:
            from_email = base_template.get_from_email()
            reply_to = [base_template.reply_to] if base_template.reply_to else None
        else:
            from_email = f'{settings.DEFAULT_FROM_NAME} <{settings.DEFAULT_FROM_EMAIL}>'
            reply_to = None
        self.from_email = from_email
        self.reply_to = reply_to

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        if self.connection is None:
            return
        self.connection.close()
        self.connection = None

    def _apply_headers(self, msg: EmailMessage) -> None:
        if self.from_email:
            msg.from_email = self.from_email
        if self.reply_to:
            msg.reply_to = self.reply_to

    def send(self, msg: EmailMessage) -> bool:
        """Send `msg` now and return whether the backend accepted it."""
        self._apply_headers(msg)
        if self.connection is None:
            self.connection = get_connection()
            self.connection.open()
        return bool(self.connection.send_messages([msg]))

    def queue(self, msg: EmailMessage):
        self._apply_headers(msg)
        self.messages.append(msg)

    def send_all(self) -> int:
        with get_connection() as connection:
            num_sent = connection.send_messages(self.messages)
            return num_sent
