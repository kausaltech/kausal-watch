import os
from mimetypes import guess_type

from django.db import models
from django.http import Http404
from django.http.response import FileResponse, HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _
from django.urls import NoReverseMatch
from django.views.decorators.cache import cache_control

from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework import serializers
from rest_framework.reverse import reverse
from image_cropping import ImageRatioField
from easy_thumbnails.files import get_thumbnailer


def image_upload_path(instance, filename):
    file_extension = os.path.splitext(filename)[1]
    return 'images/%s/%s%s' % (instance._meta.model_name, instance.id, file_extension)


class ModelWithImage(models.Model):
    image = models.ImageField(
        blank=True, upload_to=image_upload_path, verbose_name=_('image'),
        height_field='image_height', width_field='image_width'
    )
    image_cropping = ImageRatioField('image', '1280x720', verbose_name=_('image cropping'))
    image_height = models.PositiveIntegerField(null=True, editable=False)
    image_width = models.PositiveIntegerField(null=True, editable=False)

    def get_image_url(self, request):
        if not request or not self.image:
            return None

        url = None
        try:
            url = reverse(
                '%s-image' % self._meta.model_name, request=request,
                kwargs=dict(pk=self.pk)
            )
        except NoReverseMatch:
            pass

        return url

    class Meta:
        abstract = True


class ModelWithImageSerializerMixin(serializers.Serializer):
    image_url = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        image_fields = ['image', 'image_cropping', 'image_width', 'image_height']
        for field in image_fields:
            if field not in self.fields:
                continue
            del self.fields[field]

    def get_image_url(self, obj):
        request = self.context.get('request')
        return obj.get_image_url(request)


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


class ModelWithImageViewMixin:
    @cache_control(max_age=3600)
    @action(detail=True)
    def image(self, request, pk=None):
        qs = self.get_queryset()
        obj = get_object_or_404(qs, pk=pk)
        height = request.GET.get('height', None)
        width = request.GET.get('width', None)
        image = obj.image
        if image is None:
            raise Http404

        if height or width:
            try:
                dim = determine_image_dim(image, width, height)
            except ValueError as verr:
                return HttpResponseBadRequest(str(verr))
        else:
            dim = None

        if not dim:
            out_image = obj.image
            filename = out_image.name
        else:
            out_image = get_thumbnailer(obj.image).get_thumbnail({
                'size': dim,
                'box': obj.image_cropping,
                'crop': True,
                'detail': True,
            })
            filename = "%s-%dx%d%s" % (obj.image.name, dim[0], dim[1], os.path.splitext(out_image.name)[1])

        # FIXME: Use SendFile headers instead of Django output when not in debug mode
        out_image.seek(0)
        resp = FileResponse(out_image, content_type=guess_type(filename, False)[0])
        resp["Content-Disposition"] = "attachment; filename=%s" % os.path.basename(filename)
        return resp
