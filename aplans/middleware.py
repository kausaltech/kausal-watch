from __future__ import annotations

import json
import re
from collections.abc import Mapping

from django import http
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import MiddlewareNotUsed
from django.db import connection, transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import sync_and_async_middleware
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import activate, gettext_lazy as _
from wagtail.users.models import UserProfile

import sentry_sdk
from asgiref.sync import iscoroutinefunction
from loguru import logger
from social_core.exceptions import SocialAuthBaseException

from aplans.cache import WatchObjectCache
from aplans.context_vars import ctx_request
from aplans.types import WatchAdminRequest, WatchRequest
from aplans.utils import get_hostname_redirect_response

from actions.models import Plan


class SocialAuthExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        strategy = getattr(request, 'social_strategy', None)
        if strategy is None or settings.DEBUG:
            # Let the exception fly
            return None

        if not isinstance(exception, SocialAuthBaseException):
            return None

        backend = getattr(request, 'backend', None)
        backend_name = getattr(backend, 'name', 'unknown-backend')

        sentry_sdk.capture_exception(exception)

        message = _('Login was unsuccessful.')
        messages.error(request, message, extra_tags='social-auth ' + backend_name)
        return redirect(reverse('wagtailadmin_login'))


def get_active_admin_plan(self):
    # FIXME: Use session instead?
    return self.user.get_active_admin_plan()


class AdminMiddleware(MiddlewareMixin):
    def process_view(self, request: WatchAdminRequest, *args, **kwargs) -> None:
        with sentry_sdk.start_span(name='AdminMiddleware.process_view 1'):
            request.watch_cache = WatchObjectCache()

        user = request.user
        if not user or not user.is_authenticated or not user.is_staff:
            return

        profile = UserProfile.get_for_user(user)
        plan = request.user.get_active_admin_plan()
        if plan is not None:
            request.admin_cache = request.watch_cache.for_plan(plan)
        # If the user has already set the UI language, use that one.
        # Otherwise, default to the primary language of the plan.
        if profile.preferred_language and profile.preferred_language in (x[0] for x in settings.LANGUAGES):
            activate(profile.preferred_language)
        else:
            profile.preferred_language = plan.primary_language
            profile.save(update_fields=['preferred_language'])

        # Inject the helper function into the request object
        request.get_active_admin_plan = get_active_admin_plan.__get__(request, WatchAdminRequest)  # type: ignore[method-assign]

        if not plan.site_id:
            return
        setattr(request, '_wagtail_site', plan.site)  # noqa: B010

        # If it's an admin method that changes something, invalidate Plan-related
        # GraphQL cache.
        if request.method in ('POST', 'PUT', 'DELETE'):
            ADMIN_IGNORE_PATHS = [
                '/admin/editing-sessions/',
                '/admin/login/',
                '/admin/logout/',
            ]
            rest_api_path_match = re.match(r'^\/v1\/plan\/([0-9]+)\/', request.path)
            plan_to_invalidate: Plan | None = None
            if rest_api_path_match:
                plan_id = int(rest_api_path_match.group(1))
                plan_to_invalidate = Plan.objects.get(id=plan_id)
            elif re.match(r'^/(admin|wadmin)/', request.path):
                plan_to_invalidate = plan
                if any(request.path.startswith(ignore_path) for ignore_path in ADMIN_IGNORE_PATHS):
                    plan_to_invalidate = None
            if plan_to_invalidate:
                transaction.on_commit(lambda: plan_to_invalidate.invalidate_cache())


class RequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: WatchRequest):
        log_context = {}
        if request.session and request.session.session_key:
            log_context['session'] = str(request.session.session_key)[0:8]
        with ctx_request.activate(request), logger.contextualize(**log_context):
            return self.get_response(request)


QUERIES_TO_IGNORE = ['BEGIN', 'COMMIT', 'ROLLBACK']


class PrintQueryCountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):  # noqa: C901
        response = self.get_response(request)
        queries = [q for q in connection.queries if q['sql'] not in QUERIES_TO_IGNORE]

        sqltime = 0.0
        for query in queries:
            sqltime += float(query["time"])
        sqltime = round(1000 * sqltime)

        query_count = len(queries)
        if query_count == 0:
            return response
        if query_count >= 100:
            level = 'ERROR'
        elif query_count >= 50:
            level = 'WARNING'
        elif query_count >= 20:
            level = 'INFO'
        else:
            level = 'DEBUG'

        graphql_operation_name = '-'
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            pass
        except http.RawPostDataException:
            pass
        except Exception as e:
            logger.error(e)
        else:
            if isinstance(body, Mapping) and 'operationName' in body:
                graphql_operation_name = str(body.get('operationName', '-'))

        logger.log(level, f"⛁ {query_count} SQL queries took {sqltime} ms {request.path} {graphql_operation_name}")
        return response




@sync_and_async_middleware
def hostname_redirect_middleware(get_response):
    """
    Redirect requests based on hostname wildcard patterns.

    Checks incoming request hostname against patterns defined in settings.REDIRECT_HOSTNAMES
    and performs HTTP 301 redirects when a match is found.

    Wildcard rules:
        - '*' matches any valid subdomain part (letters, numbers, hyphens)
        - '*' does NOT match multiple levels (no periods in matched part)
        - Example: '*.app.example.com' matches 'test.app.example.com'
                   but NOT 'foo.bar.app.example.com'

    Settings format:
        REDIRECT_HOSTNAMES = (
            ('*.app.example.com', 'app.example.com'),
            ('old.example.com', 'new.example.com'),
        )
    """
    redirect_hostnames = getattr(settings, 'REDIRECT_HOSTNAMES', ())
    allowed_non_wildcard_hosts = set(
        h for h in getattr(settings, 'ALLOWED_HOSTS', [])
        if not h.startswith('.')
    )
    if not redirect_hostnames:
        raise MiddlewareNotUsed('REDIRECT_HOSTNAMES not configured. This is only an error if hostname redirects must be active.')
    if iscoroutinefunction(get_response):
        async def middleware(request: http.HttpRequest):  # pyright: ignore[reportRedeclaration]  # type: ignore[misc]  # noqa: ANN202
            redirect_response = get_hostname_redirect_response(request, redirect_hostnames, allowed_non_wildcard_hosts)
            if redirect_response:
                return redirect_response
            return await get_response(request)
    else:
        def middleware(request: http.HttpRequest):  # type: ignore[misc]  # noqa: ANN202
            redirect_response = get_hostname_redirect_response(request, redirect_hostnames, allowed_non_wildcard_hosts)
            if redirect_response:
                return redirect_response
            return get_response(request)

    return middleware


# Backward compatibility alias for existing tests and settings
HostnameRedirectMiddleware = hostname_redirect_middleware
