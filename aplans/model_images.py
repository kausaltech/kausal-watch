import os
import re
from mimetypes import guess_type

from django.db import models
from django.http import Http404
from django.http.response import FileResponse, HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404

from sentry_sdk import capture_exception


def image_upload_path(instance, filename):
    file_extension = os.path.splitext(filename)[1]
    return 'images/%s/%s%s' % (instance._meta.model_name, instance.id, file_extension)


def determine_image_dim(image, width, height):
    for name in ('width', 'height'):
        x = locals()[name]
        if x is None:
            continue
        try:
            x = int(x)
            if x <= 0:
                raise ValueError()
            if x > 4000:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("invalid %s dimension: %s" % (name, x))

    if width is not None:
        width = int(width)
    if height is not None:
        height = int(height)

    ratio = image.width / image.height
    if not height:
        height = width / ratio
    elif not width:
        width = height * ratio

    return (width, height)


class ModelWithImageSerializerMixin(serializers.Serializer):
    image_url = serializers.SerializerMethodField()
    main_image = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        image_fields = ['image', 'image_cropping', 'image_width', 'image_height']
        for field in image_fields:
            if field not in self.fields:
                continue
            del self.fields[field]

    def get_image_url(self, obj):
        # Disable functionality for now
        return None

    def get_main_image(self, obj):
        # Disable functionality for now
        return None


class ModelWithImageViewMixin:
    @cache_control(max_age=3600)
    @action(detail=True)
    def image(self, request, pk=None):
        raise Http404
