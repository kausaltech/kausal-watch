import re
from typing import Optional, Any
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


class RootRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        request = self.request
        client = Client.objects.for_request(request).first()
        if client is None:
            url = reverse('graphql')
        else:
            url = reverse('wagtailadmin_home')
        return url


class WadminRedirectView(RedirectView):
    permanent = True

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> Optional[str]:
        new_path = re.sub('^/wadmin', '/admin', self.request.get_full_path())
        return new_path
