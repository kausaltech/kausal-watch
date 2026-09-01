"""
Django OAuth authentication middleware for MCP.

This module provides ASGI middleware that enforces authentication for the MCP
endpoint, returning proper OAuth 2.0 error responses when authentication fails.
Token validation is handled by GeneralRequestMiddleware (kausal_common/asgi/middleware.py).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.conf import settings

from loguru import logger

from kausal_common.users import user_or_none

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logger.bind(name='mcp.auth')


class MCPAuthMiddleware:
    """
    ASGI middleware that enforces authentication for MCP endpoints.

    This middleware checks if the request has an authenticated Django user
    (set by GeneralRequestMiddleware) and returns a 401 response with proper
    OAuth 2.0 headers if not authenticated.

    The WWW-Authenticate header includes the resource_metadata URL pointing
    to our RFC 9728 Protected Resource Metadata endpoint, which allows
    MCP clients to discover our OAuth server for authentication.
    """

    def __init__(self, app: ASGIApp, resource_path: str = 'mcp'):
        self.app = app
        self.resource_path = resource_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        user = user_or_none(scope.get('user'))
        if user is None:
            await self._send_auth_error(send)
            return

        # Allow only for superusers for now
        if not user.is_superuser:
            await self._send_forbidden_error(send)
            return

        await self.app(scope, receive, send)

    async def _send_forbidden_error(self, send: Send) -> None:
        """Send a 403 Forbidden response."""
        await send({
            'type': 'http.response.start',
            'status': 403,
            'headers': [
                (b'content-type', b'application/json'),
            ],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Forbidden',
        })
        logger.warning('MCP auth error: forbidden request')

    async def _send_auth_error(self, send: Send) -> None:
        """Send a 401 Unauthorized response with OAuth 2.0 headers."""
        base_url = getattr(settings, 'ADMIN_BASE_URL', '').rstrip('/')
        resource_metadata_url = f'{base_url}/.well-known/oauth-protected-resource/{self.resource_path}'

        # Build WWW-Authenticate header per RFC 6750 and RFC 9728
        www_auth_parts = [
            'error="invalid_token"',
            'error_description="Authentication required"',
            f'resource_metadata="{resource_metadata_url}"',
        ]
        www_authenticate = f'Bearer {", ".join(www_auth_parts)}'

        body = {
            'error': 'invalid_token',
            'error_description': 'Authentication required. Use the resource_metadata URL to discover the OAuth server.',
        }
        body_bytes = json.dumps(body).encode()

        await send({
            'type': 'http.response.start',
            'status': 401,
            'headers': [
                (b'content-type', b'application/json'),
                (b'content-length', str(len(body_bytes)).encode()),
                (b'www-authenticate', www_authenticate.encode()),
                (b'access-control-allow-origin', b'*'),
            ],
        })

        await send({
            'type': 'http.response.body',
            'body': body_bytes,
        })

        logger.debug('MCP auth error: unauthenticated request')


# summary metrics
# plans that are inactive
# start tracking analytics
