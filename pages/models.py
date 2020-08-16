from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltrans.fields import TranslationField
from wagtail.admin.edit_handlers import (
    FieldPanel, MultiFieldPanel, StreamFieldPanel,
)
from wagtail.core.models import Page
from wagtail.core.fields import StreamField, RichTextField
from wagtail.core import blocks
from wagtail.images.edit_handlers import ImageChooserPanel

from .blocks import (
    QuestionAnswerBlock, IndicatorHighlightsBlock, ActionHighlightsBlock, FrontPageHeroBlock
)


PAGE_TRANSLATED_FIELDS = ['title', 'slug', 'url_path']


class AplansPage(Page):
    i18n = models.JSONField(blank=True, null=True)

    content_panels = [
        FieldPanel('title', classname="full title"),
    ]

    promote_panels = [
        MultiFieldPanel([
            FieldPanel('slug'),
            FieldPanel('seo_title'),
            FieldPanel('show_in_menus'),
            FieldPanel('search_description'),
        ], _('Common page configuration')),
    ]

    class Meta:
        abstract = True


class PlanRootPage(AplansPage):
    body = StreamField([
        ('front_page_hero', FrontPageHeroBlock()),
        ('indicator_highlights', IndicatorHighlightsBlock()),
        ('action_highlights', ActionHighlightsBlock()),
    ])

    content_panels = AplansPage.content_panels + [
        StreamFieldPanel('body'),
    ]

    parent_page_types = []
    subpage_types = ['pages.StaticPage']


class StaticPage(AplansPage):
    header_image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name=_('Header image'), help_text=_('Image to use in the header for this page')
    )
    lead_paragraph = RichTextField(
        null=True, blank=True,
        verbose_name=_('Lead paragraph'),
        help_text=_('Lead paragraph right under the heading'),
    )
    body = StreamField([
        ('heading', blocks.CharBlock(classname='full title', label=_('Heading'))),
        ('paragraph', blocks.RichTextBlock(label=_('Paragraph'))),
        ('qa_section', QuestionAnswerBlock(label=_('Questions & Answers'), icon='help')),
    ])

    content_panels = AplansPage.content_panels + [
        ImageChooserPanel('header_image'),
        StreamFieldPanel('body'),
    ]
