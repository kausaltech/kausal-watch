import re

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import activate
from django.utils.translation import gettext_lazy as _

import sentry_sdk
from social_core.exceptions import SocialAuthBaseException
from wagtail.users.models import UserProfile

from aplans.types import WatchAdminRequest


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
        return redirect(reverse('admin:login'))


def get_active_admin_plan(self):
    # FIXME: Use session instead?
    return self.user.get_active_admin_plan()


class AdminMiddleware(MiddlewareMixin):
    def process_view(self, request, *args, **kwargs):
        user = request.user
        if not user or not user.is_authenticated or not user.is_staff:
            return

        profile = UserProfile.get_for_user(user)
        plan = request.user.get_active_admin_plan()

        # If the user has already set the UI language, use that one.
        # Otherwise, default to the primary language of the plan.
        if profile.preferred_language and profile.preferred_language in (x[0] for x in settings.LANGUAGES):
            activate(profile.preferred_language)
        else:
            profile.preferred_language = plan.primary_language
            profile.save(update_fields=['preferred_language'])

        # Inject the helper function into the request object
        request.get_active_admin_plan = get_active_admin_plan.__get__(request, WatchAdminRequest)

        if not plan.site_id:
            return
        request._wagtail_site = plan.site

        # If it's an admin method that changes something, invalidate Plan-related
        # GraphQL cache.
        if request.method in ('POST', 'PUT', 'DELETE') and re.match(r'^/(admin|wadmin)/', request.path):
            def invalidate_cache():
                plan.invalidate_cache()
            transaction.on_commit(invalidate_cache)
