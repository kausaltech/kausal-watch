from wagtail.documents.models import Document as WagtailDocument, AbstractDocument
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class AplansDocument(AbstractDocument):
    admin_form_fields = WagtailDocument.admin_form_fields

    class Meta:
        verbose_name = _('document')
        verbose_name_plural = _('documents')

    @property
    def url(self):
        return reverse('wagtaildocs_serve', args=[self.id, self.filename])
