import os
from mimetypes import guess_type

from django.db import models
from django.http.response import FileResponse, HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.urls import NoReverseMatch

from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework import viewsets, serializers
from rest_framework.reverse import reverse
from image_cropping import ImageRatioField
from easy_thumbnails.files import get_thumbnailer


def image_upload_path(instance, filename):
    file_extension = os.path.splitext(filename)[1]
    return 'images/%s/%s%s' % (instance._meta.model_name, instance.id, file_extension)


class ModelWithImage(models.Model):
    image = models.ImageField(
        blank=True, upload_to=image_upload_path, verbose_name=_('image')
    )
    image_cropping = ImageRatioField('image', '1280x720')

    class Meta:
        abstract = True


def parse_dimension_string(dim):
    """
    Parse a dimension string ("WxH") into (width, height).

    :param dim: Dimension string
    :type dim: str
    :return: Dimension tuple
    :rtype: tuple[int, int]
    """
    a = dim.split('x')
    if len(a) != 2:
        raise ValueError('"dim" must be <width>x<height>')
    width, height = a
    try:
        width = int(width)
        height = int(height)
    except (ValueError, TypeError) as e:
        width = height = 0
    if not (width > 0 and height > 0):
        raise ValueError("width and height must be positive integers")
    # FIXME: Check allowed image dimensions better
    return (width, height)


class ModelWithImageSerializerMixin(serializers.Serializer):
    image = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'image_cropping' in self.fields:
            del self.fields['image_cropping']

    def get_image(self, obj):
        view = self.context.get('view')
        request = self.context.get('request')
        if not view or not request:
            return None
        if not obj.image:
            return None
        url = None

        for act in view.get_extra_actions():
            if act.url_name != 'image':
                continue
            try:
                url_name = '%s-%s' % (view.basename, act.url_name)
                url = reverse(url_name, kwargs=dict(pk=obj.pk), request=request)
            except NoReverseMatch:
                pass  # URL requires additional arguments, ignore
        return url


class ModelWithImageViewMixin:
    @action(detail=True)
    def image(self, request, pk=None):
        qs = self.get_queryset()
        obj = get_object_or_404(qs, pk=pk)
        dim = request.GET.get('dim', None)
        if dim:
            try:
                width, height = parse_dimension_string(dim)
            except ValueError as verr:
                return HttpResponseBadRequest(str(verr))
        else:
            width = height = None

        if not width:
            out_image = obj.image
            filename = out_image.name
        else:
            out_image = get_thumbnailer(obj.image).get_thumbnail({
                'size': (width, height),
                'box': obj.image_cropping,
                'crop': True,
                'detail': True,
            })
            filename = "%s-%dx%d%s" % (obj.image.name, width, height, os.path.splitext(out_image.name)[1])

        # FIXME: Use SendFile headers instead of Django output when not in debug mode
        out_image.seek(0)
        resp = FileResponse(out_image, content_type=guess_type(filename, False)[0])
        resp["Content-Disposition"] = "attachment; filename=%s" % os.path.basename(filename)
        return resp
