from rest_framework import viewsets
from rest_framework import renderers
from aplans.utils import register_view_helper
from aplans.model_images import ModelWithImageViewMixin
from .models import (
    StaticPage, BlogPost
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
