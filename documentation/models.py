from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from actions.models.plan import Plan
from pages.models import DefaultSlugForCopyingMixin

if TYPE_CHECKING:
    from kausal_common.models.types import FK


class DocumentationRootPage(DefaultSlugForCopyingMixin, Page):
    plan: FK[Plan] = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='documentation_root_pages')

    content_panels = [
        FieldPanel('title'),
    ]
    promote_panels = []

    parent_page_types = ['wagtailcore.Page']  # Can only be under the global root page
    subpage_types = ['DocumentationPage']
    is_creatable = False  # Only let this be created programmatically

    # Disable Wagtail's previews because our hacks make them break
    @property
    def preview_modes(self):
        return []


class DocumentationPage(Page):
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
    ], blank=True)
    css_style = models.CharField[str, str](
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

    # Disable Wagtail's previews because our hacks make them break
    @property
    def preview_modes(self):
        return []

    class Meta:
        verbose_name = _('Documentation page')
        verbose_name_plural = _('Documentation pages')
