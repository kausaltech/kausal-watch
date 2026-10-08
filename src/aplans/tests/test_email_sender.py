from __future__ import annotations

from unittest.mock import patch

from django.core import mail
from django.core.mail import EmailMessage

from aplans.email_sender import EmailSender


def test_send_applies_sender_headers_and_reports_delivery(settings):
    settings.DEFAULT_FROM_NAME = 'Sender'
    settings.DEFAULT_FROM_EMAIL = 'sender@example.com'
    with EmailSender() as sender:
        assert sender.send(EmailMessage(subject='s', body='b', to=['a@example.com']))
    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == 'Sender <sender@example.com>'


def test_send_reports_a_message_the_backend_did_not_accept():
    with (
        patch('django.core.mail.backends.locmem.EmailBackend.send_messages', return_value=0),
        EmailSender() as sender,
    ):
        assert not sender.send(EmailMessage(subject='s', body='b', to=['a@example.com']))


def test_no_connection_is_opened_when_nothing_is_sent():
    with patch('aplans.email_sender.get_connection') as get_connection, EmailSender():
        pass
    get_connection.assert_not_called()


def test_sends_share_one_connection():
    with patch('django.core.mail.backends.locmem.EmailBackend.open') as open_connection, EmailSender() as sender:
        sender.send(EmailMessage(subject='s', body='b', to=['a@example.com']))
        sender.send(EmailMessage(subject='s', body='b', to=['b@example.com']))
    open_connection.assert_called_once()
