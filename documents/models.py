from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail.documents.models import AbstractDocument, Document as WagtailDocument
from wagtail.search.queryset import SearchableQuerySetMixin

from kausal_common.models.types import ModelManager

from users.models import User

if TYPE_CHECKING:
    from kausal_common.models.types import FK


class AplansDocumentQuerySet(SearchableQuerySetMixin, models.QuerySet['AplansDocument']):
    pass


_AplansDocumentManager = models.Manager.from_queryset(AplansDocumentQuerySet)
class AplansDocumentManager(ModelManager['AplansDocument', AplansDocumentQuerySet], _AplansDocumentManager): ...
del _AplansDocumentManager


class AplansDocument(AbstractDocument):
    admin_form_fields = WagtailDocument.admin_form_fields
    uploaded_by_user: FK[User | None] = models.ForeignKey(
        User,
        verbose_name=_("uploaded by user"),
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
    )
    uploaded_by_user.wagtail_reference_index_ignore = True  # type: ignore[attr-defined]

    objects: ClassVar[AplansDocumentManager] = AplansDocumentManager()  # type: ignore[assignment]

    class Meta:
        verbose_name = _('document')
        verbose_name_plural = _('documents')

    @property
    def url(self):
        return reverse('wagtaildocs_serve', args=[self.pk, self.filename])
