from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from notifications.notifications import NotificationType

if TYPE_CHECKING:
    from argparse import ArgumentParser


def add_notification_delivery_arguments(parser: ArgumentParser) -> None:
    type_choices = [x.identifier for x in NotificationType]
    parser.add_argument('--force-to', type=str, help='Rewrite the To field and send all emails to this address')
    parser.add_argument('--limit', type=int, help='Do not send more than this many emails')
    parser.add_argument('--only-type', type=str, choices=type_choices, help='Send only notifications of this type')
    parser.add_argument('--only-email', type=str, help='Send only the notifications that go to this email')
    parser.add_argument('--noop', action='store_true', help='Do not actually send the emails')
    parser.add_argument(
        '--dump',
        metavar='FILE',
        type=str,
        help='Dump generated MJML and HTML files',
    )
    parser.add_argument('--time', type=datetime.fromisoformat, help='Override current time (ISO format)')
