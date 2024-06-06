import re
from django.conf import settings
from django.db import transaction, connection
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

from loguru import logger
import sentry_sdk
from social_core.exceptions import SocialAuthBaseException
from wagtail.admin import messages
from wagtail.users.models import UserProfile
from aplans.cache import WatchObjectCache

from aplans.context_vars import set_request
from aplans.types import WatchAdminRequest, WatchRequest
from actions.models import Plan


class SocialAuthExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        strategy = getattr(request, 'social_strategy', None)
        if strategy is None or settings.DEBUG:
            # Let the exception fly
            return

        if not isinstance(exception, SocialAuthBaseException):
            return

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
    def process_view(self, request: WatchAdminRequest, *args, **kwargs):
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
            log_context['session'] = str(request.session.session_key)
        with set_request(request), logger.contextualize(**log_context):
            return self.get_response(request)


class PrintQueryCountMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        sqltime = 0
        for query in connection.queries:
            sqltime += float(query["time"])
        sqltime = round(1000 * sqltime)

        query_count = len(connection.queries)
        level = 'INFO'
        if query_count >= 50:
            level = 'WARNING'
        if query_count >= 100:
            level = 'ERROR'
        logger.log(level, f"⛁ {query_count} SQL queries took {sqltime} ms")
        return response
