from collections import OrderedDict
from urllib.parse import urlencode

from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.views.generic.base import RedirectView
from django.contrib.auth import logout, REDIRECT_FIELD_NAME
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from .models import Client


LANGUAGE_FIELD_NAME = 'ui_locales'


class LogoutView(DjangoLogoutView):
    def dispatch(self, request, *args, **kwargs):
        was_authenticated = request.user.is_authenticated
        session = request.session
        end_session_url = session.get('social_auth_end_session_url')
        if end_session_url:
            self.next_page = end_session_url
        ret = super().dispatch(request, *args, **kwargs)
        if was_authenticated:
            messages.success(request, _("You have been successfully logged out."))
        return ret


class LogoutCompleteView(DjangoLogoutView):
    def dispatch(self, request, *args, **kwargs):
        return HttpResponseRedirect(self.get_next_page())


class LoginView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        # We make sure the user is logged out first, because otherwise
        # PSA will enter the connect flow where a new social authentication
        # method is connected to an existing user account.
        request = self.request
        logout(request)

        client = Client.objects.for_request(request).first()
        if client is None:
            # Fallback to Tunnistamo for now
            url = reverse('social:begin', kwargs=dict(backend='tunnistamo'))
        else:
            url = reverse('social:begin', kwargs=dict(backend='azure_ad'))

        redirect_to = self.request.GET.get(REDIRECT_FIELD_NAME)
        lang = self.request.GET.get(LANGUAGE_FIELD_NAME)

        query_params = OrderedDict()
        if redirect_to:
            query_params[REDIRECT_FIELD_NAME] = redirect_to
        if lang:
            query_params[LANGUAGE_FIELD_NAME] = lang
        if query_params:
            url += '?' + urlencode(query_params)

        return url
