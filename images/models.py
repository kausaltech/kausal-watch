from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtail.images.models import AbstractImage, AbstractRendition
from wagtail.images.models import Image as WagtailImage


class AplansImage(AbstractImage):
    admin_form_fields = WagtailImage.admin_form_fields + ('image_credit', 'alt_text')

    image_credit = models.CharField(max_length=254, blank=True)
    alt_text = models.CharField(max_length=254, blank=True)

    class Meta:
        verbose_name = _('image')
        verbose_name_plural = _('images')


class AplansRendition(AbstractRendition):
    image = models.ForeignKey(AplansImage, related_name='renditions', on_delete=models.CASCADE)

    def get_fqdn_attrs(self, request):
        ret = self.attrs_dict.copy()
        ret['src'] = request.build_absolute_uri(ret['src'])
        return ret

    class Meta:
        unique_together = (
            ('image', 'filter_spec', 'focal_point_key'),
        )
