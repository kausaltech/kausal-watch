from __future__ import annotations

from wagtail.images.formats import get_image_format
from wagtail.images.rich_text import ImageEmbedHandler as WagtailImageEmbedHandler


class ImageEmbedHandler(WagtailImageEmbedHandler):
    """
    Custom image embed handler that injects image credit as a data attribute.

    This ensures that images embedded in rich text fields carry their
    ``image_credit`` metadata so the frontend can render bylines.
    """

    identifier = 'image'

    @classmethod
    def expand_db_attributes_many(cls, attrs_list: list[dict]) -> list[str]:
        images = cls.get_many(attrs_list)

        tags: list[str] = []
        for attrs, image in zip(attrs_list, images, strict=True):
            if image:
                image_format = get_image_format(attrs['format'])
                extra_attributes: dict[str, str] = {}
                image_credit = getattr(image, 'image_credit', '')
                if image_credit:
                    extra_attributes['data-image-credit'] = image_credit
                tag = image_format.image_to_html(image, attrs.get('alt', ''), extra_attributes=extra_attributes)
            else:
                tag = '<img alt="">'
            tags.append(tag)

        return tags
