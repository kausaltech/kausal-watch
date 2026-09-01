"""
ASGI config for watch project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/asgi/
"""

from __future__ import annotations

import os
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, cast

from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from kausal_common.asgi.middleware import HTTPMiddleware, WebSocketMiddleware

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.urls import URLPattern, URLResolver

    from fastmcp.server.http import StarletteWithLifespan

    from mcp_server.auth import MCPAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')

django_asgi_app = get_asgi_application()


class AuthGraphQLProtocolTypeRouter(ProtocolTypeRouter):
    def _get_mcp_server_app(self) -> tuple[StarletteWithLifespan, MCPAuthMiddleware]:
        from mcp_server.auth import MCPAuthMiddleware
        from mcp_server.server import mcp as mcp_server

        mcp_asgi_app = mcp_server.http_app(path='/mcp', stateless_http=True)
        mcp_with_auth = MCPAuthMiddleware(mcp_asgi_app, resource_path='mcp')
        return mcp_asgi_app, mcp_with_auth

    def __init__(self):
        from django.conf import settings
        from django.urls import re_path

        from channels.routing import URLRouter

        from .graphql_views import WatchGraphQLHTTPConsumer, WatchGraphQLWSConsumer
        from .schema import async_schema, schema

        re_path_any = cast('Callable[[str, Any], URLPattern | URLResolver]', re_path)

        gql_url_pattern = r'^v1/graphql/$'
        http_urls: list[URLPattern | URLResolver] = []
        # debug-toolbar does not work with generic ASGI apps. If it's enabled,
        # we route the graphql endpoint to the django app.
        if not settings.ENABLE_DEBUG_TOOLBAR:
            graphql_asgi_app = HTTPMiddleware(WatchGraphQLHTTPConsumer.as_asgi(schema=schema))
            http_urls.append(re_path_any(gql_url_pattern, graphql_asgi_app))
        if not settings.DEBUG:
            http_urls.append(re_path_any(r'^static/', Mount(path='/static', app=StaticFiles(directory=settings.STATIC_ROOT))))

        # MCP server with our own auth middleware (wraps the FastMCP app)
        # Use stateless_http=True to avoid session tracking issues on server restart
        if settings.ENABLE_MCP_SERVER:
            if find_spec('fastmcp') is None:
                raise RuntimeError('MCP server is enabled, but fastmcp is not installed.')
            mcp_asgi_app, mcp_with_auth = self._get_mcp_server_app()
            http_urls.append(re_path_any(r'^mcp[/]?$', HTTPMiddleware(mcp_with_auth)))
        else:
            mcp_asgi_app = None
        http_urls.append(re_path_any(r'^', django_asgi_app))

        type_routing = {
            'http': URLRouter(
                http_urls,  # pyright: ignore[reportArgumentType]
            ),
            'websocket': WebSocketMiddleware(
                URLRouter(
                    [
                        re_path_any(  # pyright: ignore[reportArgumentType]
                            gql_url_pattern,
                            WatchGraphQLWSConsumer.as_asgi(schema=async_schema),
                        ),
                    ],
                ),
            ),
        }
        if mcp_asgi_app:
            type_routing['lifespan'] = mcp_asgi_app.router.lifespan

        super().__init__(type_routing)


application = AuthGraphQLProtocolTypeRouter()
