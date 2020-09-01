import sentry_sdk
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import activate
from django.utils.translation import ugettext_lazy as _
from social_core.exceptions import SocialAuthBaseException
from wagtail.users.models import UserProfile


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


class AdminMiddleware(MiddlewareMixin):
    def process_view(self, request, *args, **kwargs):
        user = request.user
        if not user or not user.is_authenticated or not user.is_staff:
            return

        profile = UserProfile.get_for_user(user)
        plan = request.user.get_active_admin_plan()

        if profile.preferred_language and profile.preferred_language in (x[0] for x in settings.LANGUAGES):
            activate(profile.preferred_language)
        else:
            profile.preferred_language = plan.primary_language
            profile.save(update_fields=['preferred_language'])

        if not plan.site_id:
            return
        request._wagtail_site = plan.site
