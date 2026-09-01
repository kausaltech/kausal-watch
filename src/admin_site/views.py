from __future__ import annotations

import re
from typing import Any

from django.views.generic.base import RedirectView


class WadminRedirectView(RedirectView):
    permanent = True

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> str | None:
        # TODO: Add #from-redirect to the URL once the US customers have migrated to the new admin (AKA updated their bookmarks).
        # This is not added now to avoid confusing double redirect notice for migrating users.
        new_path = re.sub('^/wadmin', '/admin', self.request.get_full_path())
        return new_path
