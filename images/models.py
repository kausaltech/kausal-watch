from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.images.models import AbstractImage, Image as WagtailImage, AbstractRendition


class AplansImage(AbstractImage):
    admin_form_fields = WagtailImage.admin_form_fields

    class Meta:
        verbose_name = _('image')
        verbose_name_plural = _('images')


class AplansRendition(AbstractRendition):
    image = models.ForeignKey(AplansImage, related_name='renditions', on_delete=models.CASCADE)

    class Meta:
        unique_together = (
            ('image', 'filter_spec', 'focal_point_key'),
        )
