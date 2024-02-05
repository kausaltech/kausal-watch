from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from actions.models import Plan


class EmailSender:
    messages: list[EmailMessage]
    from_email: str | None
    reply_to: list | None

    def __init__(self, plan: Plan | None = None):
        self.messages = []
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

    def queue(self, msg):
        if self.from_email:
            msg.from_email = self.from_email
        if self.reply_to:
            msg.reply_to = self.reply_to
        self.messages.append(msg)

    def send_all(self) -> int:
        with get_connection() as connection:
            num_sent = connection.send_messages(self.messages)
            return num_sent
