from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from actions.models.plan import Plan


class DocumentationRootPage(Page):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='documentation_root_pages')

    content_panels = [
        FieldPanel('title'),
    ]
    promote_panels = []

    parent_page_types = ['wagtailcore.Page']  # Can only be under the global root page
    subpage_types = ['DocumentationPage']
    is_creatable = False  # Only let this be created programmatically


class DocumentationPage(Page):
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
    ], use_json_field=True, blank=True)
    css_style = models.CharField(
        max_length=1000, blank=True, verbose_name=_('CSS style'),
        help_text=_('CSS style to be applied to the container of the body'),
    )

    content_panels = [
        FieldPanel('title'),
        FieldPanel('body'),
    ]
    promote_panels = []
    settings_panels = [
        FieldPanel('css_style'),
    ]

    parent_page_types = [DocumentationRootPage]
    subpage_types = []

    class Meta:
        verbose_name = _('Documentation page')
        verbose_name_plural = _('Documentation pages')
