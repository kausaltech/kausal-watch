from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from rest_framework import renderers, viewsets

from kausal_common.api.utils import register_view_helper

from pages.models import StaticPage

if TYPE_CHECKING:
    from django.db.models import Model

    from kausal_common.api.utils import RegisteredAPIView

BlogPost: type[Model] | None
try:
    BlogPost = apps.get_model('content', 'BlogPost')
except LookupError:
    BlogPost = None

all_views: list[RegisteredAPIView] = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


@register_view
class StaticPageViewSet(viewsets.GenericViewSet):
    queryset = StaticPage.objects.all()
    renderer_classes = [renderers.JSONRenderer]


if BlogPost is not None:

    @register_view
    class BlogPostViewSet(viewsets.GenericViewSet):
        queryset = BlogPost.objects.all()  # type: ignore[union-attr]
        renderer_classes = [renderers.JSONRenderer]
