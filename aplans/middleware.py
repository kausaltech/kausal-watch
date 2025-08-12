from __future__ import annotations

import json
import re
from collections.abc import Mapping

from django import http
from django.conf import settings
from django.contrib import messages
from django.db import connection, transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import activate, gettext_lazy as _
from wagtail.users.models import UserProfile

import sentry_sdk
from loguru import logger
from social_core.exceptions import SocialAuthBaseException

from aplans.cache import WatchObjectCache
from aplans.context_vars import ctx_request
from aplans.types import WatchAdminRequest, WatchRequest

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
        request._wagtail_site = plan.site  # type: ignore[attr-defined]

        # If it's an admin method that changes something, invalidate Plan-related
        # GraphQL cache.
        if request.method in ('POST', 'PUT', 'DELETE'):
            rest_api_path_match = re.match(r'^\/v1\/plan\/([0-9]+)\/', request.path)
            if rest_api_path_match:
                plan_id = int(rest_api_path_match.group(1))
                plan_to_invalidate = Plan.objects.get(id=plan_id)
            elif re.match(r'^/(admin|wadmin)/', request.path):
                plan_to_invalidate = plan
            else:
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
