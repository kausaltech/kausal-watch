import os
import re
from mimetypes import guess_type

from django.db import models
from django.http import Http404
from django.http.response import FileResponse, HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from easy_thumbnails.files import get_thumbnailer
from image_cropping import ImageRatioField
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


class ModelWithImage(models.Model):
    image = models.ImageField(
        blank=True, upload_to=image_upload_path, verbose_name=_('image'),
        height_field='image_height', width_field='image_width'
    )
    image_cropping = ImageRatioField('image', '1280x720', verbose_name=_('image cropping'))
    image_height = models.PositiveIntegerField(null=True, editable=False)
    image_width = models.PositiveIntegerField(null=True, editable=False)

    main_image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    def get_image_url(self, request, size=None):
        if not request or not self.image:
            return None

        if size is None:
            url = self.image.url
        else:
            m = re.match(r'(\d+)?(x(\d+))?', size)
            if not m:
                raise ValueError('Invalid size argument (should be "<width>x<height>")')
            width, _, height = m.groups()

            try:
                dim = determine_image_dim(self.image, width, height)
            except OSError as e:
                # Treat this as a non-fatal error but report it to Sentry anyway
                capture_exception(e)
                return None

            out_image = get_thumbnailer(self.image).get_thumbnail({
                'size': dim,
                'box': self.image_cropping,
                'crop': True,
                'detail': True,
            })
            url = out_image.url

        return request.build_absolute_uri(url)

    class Meta:
        abstract = True


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
