from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail.documents.models import AbstractDocument, Document as WagtailDocument
from wagtail.search.queryset import SearchableQuerySetMixin

from kausal_common.models.types import ModelManager
from kausal_common.models.wagtail import ignore_wagtail_reference_index

from aplans.utils import PlanRelatedModelWithRevision

from users.models import User

if TYPE_CHECKING:
    from kausal_common.models.types import FK


class AplansDocumentQuerySet(SearchableQuerySetMixin, models.QuerySet['AplansDocument']):
    pass


if TYPE_CHECKING:

    class AplansDocumentManager(ModelManager['AplansDocument', AplansDocumentQuerySet]): ...

else:
    AplansDocumentManager = ModelManager.from_queryset(AplansDocumentQuerySet)


@ignore_wagtail_reference_index(['uploaded_by_user'])
class AplansDocument(AbstractDocument, PlanRelatedModelWithRevision):
    uploaded_by_user: FK[User | None] = models.ForeignKey(
        User,
        verbose_name=_('uploaded by user'),
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
    )

    admin_form_fields = WagtailDocument.admin_form_fields

    objects: ClassVar[AplansDocumentManager] = AplansDocumentManager()  # type: ignore[assignment]

    class Meta:
        verbose_name = _('document')
        verbose_name_plural = _('documents')

    def get_plans(self):
        from actions.models.plan import Plan

        collections = self.collection.get_ancestors(inclusive=True)
        plans = Plan.objects.filter(root_collection__in=collections)
        return list(plans)

    @property
    def url(self):
        return reverse('wagtaildocs_serve', args=[self.pk, self.filename])
