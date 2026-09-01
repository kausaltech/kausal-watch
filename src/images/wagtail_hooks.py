from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from wagtail import hooks

from images.permissions import permission_policy
from images.rich_text import ImageEmbedHandler

if TYPE_CHECKING:
    from wagtail.log_actions import LogActionRegistry
    from wagtail.rich_text.feature_registry import FeatureRegistry


@hooks.register('register_rich_text_features', order=1)
def register_custom_image_embed(features: FeatureRegistry):
    """Replace Wagtail's default image embed handler with one that injects image credit."""
    features.register_embed_type(ImageEmbedHandler)


@hooks.register('construct_image_chooser_queryset')
def filter_images(qs, request):
    user = request.user
    collections = permission_policy.collections_user_has_any_permission_for(user, ['choose'], request=request)
    qs = qs.filter(collection__in=collections)
    return qs


@hooks.register('register_log_actions')
def register_image_and_file_log_actions(actions: LogActionRegistry):
    actions.register_action('file.created_or_updated', _('Create or update file'), _('File created or updated'))
