import sentry_sdk
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.utils.deprecation import MiddlewareMixin
from social_core.exceptions import SocialAuthBaseException


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
