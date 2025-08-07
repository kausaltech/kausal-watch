from rest_framework import renderers, viewsets

from kausal_common.api.utils import register_view_helper
from kausal_common.model_images import ModelWithImageViewMixin

from .models import (
    BlogPost,
    StaticPage,
)

all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


@register_view
class StaticPageViewSet(ModelWithImageViewMixin, viewsets.GenericViewSet):
    queryset = StaticPage.objects.all()
    renderer_classes = [renderers.JSONRenderer]


@register_view
class BlogPostViewSet(ModelWithImageViewMixin, viewsets.GenericViewSet):
    queryset = BlogPost.objects.all()
    renderer_classes = [renderers.JSONRenderer]
