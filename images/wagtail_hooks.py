from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from wagtail import hooks

from images.permissions import permission_policy

if TYPE_CHECKING:
    from wagtail.log_actions import LogActionRegistry


@hooks.register('construct_image_chooser_queryset')
def filter_images(qs, request):
    user = request.user
    collections = permission_policy.collections_user_has_any_permission_for(user, ['choose'], request=request)
    qs = qs.filter(collection__in=collections)
    return qs


@hooks.register('register_log_actions')
def register_image_and_file_log_actions(actions: LogActionRegistry):
    actions.register_action('file.created_or_updated', _("Create or update file"), _("File created or updated"))
