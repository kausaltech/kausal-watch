from django.core.mail import EmailMessage, get_connection


class EmailSender:
    messages: list[EmailMessage]
    from_email: str | None
    reply_to: list | None

    def __init__(self, from_email: str | None = None, reply_to: list | None = None):
        self.messages = []
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
