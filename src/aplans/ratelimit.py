from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


def client_ip_for_ratelimit(request: HttpRequest) -> str:
    """
    Resolve the originating client IP for django-ratelimit.

    Traefik terminates the LB's proxy-protocol connection and rewrites
    X-Forwarded-For with the real client IP; REMOTE_ADDR at this layer is
    the Traefik node IP. Trust the leftmost XFF entry and fall back to
    REMOTE_ADDR when the header is missing or unparseable.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    remote_addr = request.META.get('REMOTE_ADDR', '')
    candidate = xff.split(',', 1)[0].strip() if xff else remote_addr
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return remote_addr
    return candidate
