import re
from typing import Any, Optional

from django.urls import reverse
from django.views.generic.base import RedirectView


class RootRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        request = self.request
        if request.user.is_authenticated:
            url = reverse('wagtailadmin_home')
        else:
            url = reverse('graphql')
        return url


class WadminRedirectView(RedirectView):
    permanent = True

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> str | None:
        new_path = re.sub('^/wadmin', '/admin', self.request.get_full_path())
        return new_path
