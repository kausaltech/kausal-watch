from __future__ import annotations

import datetime
import os
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.images.models import AbstractImage, AbstractRendition, Filter, Image as WagtailImage

from aplans.utils import PlanRelatedModel

if TYPE_CHECKING:
    from kausal_common.models.types import FK


def truncate_filename(directories: list[str], filename: str) -> str:
    """
    Join all elements of the list `directories` and the string `filename`.

    It uses a path separator and makes sure the result fits into a Django file field.
    """

    # Adapted from wagtail/images/models.py
    full_path = os.path.join(*directories, filename)
    if len(full_path) >= 95:
        chars_to_trim = len(full_path) - 94
        prefix, extension = os.path.splitext(filename)
        filename = prefix[:-chars_to_trim] + extension
        full_path = os.path.join(*directories, filename)
    return full_path


def insert_date_directory_to_path(path: str, target_dir: str, date: datetime.date | None = None) -> str:
    if not date:
        # The instance may not yet be created, so `date` may be None even if we pass `instance.created_by`
        date = datetime.date.today()
    filename = path.removeprefix(f'{target_dir}/')
    assert filename != path  # otherwise the prefix wasn't there
    date_dir = date.strftime('%Y-%m')
    return truncate_filename([target_dir, date_dir], filename)


class AplansImage(AbstractImage, PlanRelatedModel):
    admin_form_fields = WagtailImage.admin_form_fields + ('image_credit', 'alt_text')

    image_credit: models.CharField[str, str] = models.CharField(
        max_length=254, blank=True, verbose_name=_('Image byline or credits')
    )
    alt_text: models.CharField[str, str] = models.CharField(max_length=254, blank=True, verbose_name=_('Alt text'))

    _default_manager: ClassVar[models.Manager[AplansImage]]

    class Meta:
        verbose_name = _('image')
        verbose_name_plural = _('images')

    def get_plans(self):
        from actions.models.plan import Plan

        collections = self.collection.get_ancestors(inclusive=True)
        plans = Plan.objects.filter(root_collection__in=collections)
        return list(plans)

    def get_upload_to(self, filename: str) -> str:
        path = super().get_upload_to(filename)
        return insert_date_directory_to_path(path, 'original_images', self.created_at)

    if TYPE_CHECKING:
        def get_rendition(self, filter: Filter | str) -> AplansRendition: ...  # noqa: A002


class AplansRendition(AbstractRendition):
    image: FK[AplansImage] = models.ForeignKey(AplansImage, related_name='renditions', on_delete=models.CASCADE)

    def get_fqdn_attrs(self, request):
        ret = self.attrs_dict.copy()
        ret['src'] = request.build_absolute_uri(ret['src'])
        return ret

    def get_upload_to(self, filename: str) -> str:
        path = super().get_upload_to(filename)
        return insert_date_directory_to_path(path, 'images', self.image.created_at)

    class Meta:
        unique_together = (('image', 'filter_spec', 'focal_point_key'),)
