from wagtail.images.formats import Format, register_image_format
from django.utils.translation import gettext_lazy as _

from images.models import AplansImage


class ZoomableFormat(Format):
    def image_to_html(self, image: AplansImage, alt_text, extra_attributes=None):
        orig_attrs = {
            'data-original-width': image.width,
            'data-original-height': image.height,
            'data-original-src': image.file.url
        }
        attrs = (extra_attributes or {}) | orig_attrs
        return super().image_to_html(image, alt_text, extra_attributes=attrs)


register_image_format(
    ZoomableFormat(
        'fullwidth-zoomable', _('Full width (zoomable)'), 'richtext-image full-width zoomable', 'width-800'
    )
)
