from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel, StreamFieldPanel
from wagtail.core import blocks
from wagtail.core.fields import RichTextField, StreamField
from wagtail.core.models import Page, UserPagePermissionsProxy
from wagtail.images.edit_handlers import ImageChooserPanel

from actions.blocks import ActionHighlightsBlock, ActionListBlock, CategoryListBlock
from actions.chooser import CategoryChooser
from actions.models import Category
from indicators.blocks import IndicatorBlock, IndicatorHighlightsBlock

from .blocks import FrontPageHeroBlock, QuestionAnswerBlock

PAGE_TRANSLATED_FIELDS = ['title', 'slug', 'url_path']


class AplansPage(Page):
    i18n = models.JSONField(blank=True, null=True)

    content_panels = [
        FieldPanel('title', classname="full title"),
    ]

    settings_panels = [
        MultiFieldPanel([
            FieldPanel('slug'),
            FieldPanel('seo_title'),
            FieldPanel('show_in_menus'),
            FieldPanel('search_description'),
        ], _('Common page configuration')),
    ]

    promote_panels = []

    class Meta:
        abstract = True


class PlanRootPage(AplansPage):
    body = StreamField([
        ('front_page_hero', FrontPageHeroBlock(label=_('Front page hero block'))),
        ('category_list', CategoryListBlock(label=_('Category list'))),
        ('indicator', IndicatorBlock(label=_('Indicator'))),
        ('indicator_highlights', IndicatorHighlightsBlock(label=_('Indicator highlights'))),
        ('action_highlights', ActionHighlightsBlock(label=_('Action highlights'))),
    ])

    content_panels = AplansPage.content_panels + [
        StreamFieldPanel('body'),
    ]

    parent_page_types = []


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
    ], null=True, blank=True)

    content_panels = AplansPage.content_panels + [
        ImageChooserPanel('header_image'),
        StreamFieldPanel('body'),
    ]


class CategoryPage(AplansPage):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=False, verbose_name=_('Category'),
    )
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('indicator', IndicatorBlock(label=_('Indicator'))),
        ('action_list', ActionListBlock(label=_('Action list')))
    ])

    content_panels = AplansPage.content_panels + [
        FieldPanel('category', widget=CategoryChooser),
        StreamFieldPanel('body'),
    ]

    parent_page_types = [PlanRootPage, StaticPage, 'CategoryPage']
    subpage_types = [StaticPage, 'CategoryPage']
