from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLImage, GraphQLStreamfield, GraphQLString
from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel, StreamFieldPanel
from wagtail.core import blocks
from wagtail.core.fields import StreamField
from wagtail.core.models import Page
from wagtail.images.edit_handlers import ImageChooserPanel

from actions.blocks import ActionHighlightsBlock, ActionListBlock, CategoryListBlock
from actions.chooser import CategoryChooser
from actions.models import Category
from indicators.blocks import IndicatorGroupBlock, IndicatorHighlightsBlock, IndicatorShowcaseBlock
from .blocks import FrontPageHeroBlock, QuestionAnswerBlock

PAGE_TRANSLATED_FIELDS = ['title', 'slug', 'url_path']


class AplansPage(Page):
    i18n = models.JSONField(blank=True, null=True)
    show_in_footer = models.BooleanField(default=False, verbose_name=_('show in footer'),
                                         help_text=_('Should the page be shown in the footer?'),)

    content_panels = [
        FieldPanel('title', classname="full title"),
    ]

    settings_panels = [
        MultiFieldPanel([
            FieldPanel('slug'),
            FieldPanel('seo_title'),
            FieldPanel('show_in_menus'),
            FieldPanel('show_in_footer'),
            FieldPanel('search_description'),
        ], _('Common page configuration')),
    ]

    promote_panels = []

    graphql_fields = [
        GraphQLBoolean('show_in_footer'),
    ]

    class Meta:
        abstract = True


class PlanRootPage(AplansPage):
    body = StreamField([
        ('front_page_hero', FrontPageHeroBlock(label=_('Front page hero block'))),
        ('category_list', CategoryListBlock(label=_('Category list'))),
        ('indicator_group', IndicatorGroupBlock()),
        ('indicator_highlights', IndicatorHighlightsBlock(label=_('Indicator highlights'))),
        ('indicator_showcase', IndicatorShowcaseBlock()),
        ('action_highlights', ActionHighlightsBlock(label=_('Action highlights'))),
    ])

    content_panels = AplansPage.content_panels + [
        StreamFieldPanel('body'),
    ]

    parent_page_types = []

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLStreamfield('body'),
    ]

    class Meta:
        verbose_name = _('Front page')
        verbose_name_plural = _('Front pages')

    def set_url_path(self, parent):
        # Ensure the parent is the global root page
        assert self.depth == 2
        self.url_path = '/'
        return self.url_path


class EmptyPage(AplansPage):
    class Meta:
        verbose_name = _('Empty page')
        verbose_name_plural = _('Empty pages')


class StaticPage(AplansPage):
    header_image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name=_('Header image'), help_text=_('Image to use in the header for this page')
    )
    lead_paragraph = models.TextField(
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
        FieldPanel('lead_paragraph'),
        StreamFieldPanel('body'),
    ]

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLImage('header_image'),
        GraphQLString('lead_paragraph'),
        GraphQLStreamfield('body'),
    ]

    class Meta:
        verbose_name = _('Content page')
        verbose_name_plural = _('Content pages')


class CategoryPage(AplansPage):
    category = models.OneToOneField(
        Category, on_delete=models.PROTECT, null=False, verbose_name=_('Category'),
        related_name='category_page',
    )
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('indicator_group', IndicatorGroupBlock()),
        ('category_list', CategoryListBlock(label=_('Category list'))),
        ('action_list', ActionListBlock(label=_('Action list')))
    ])

    content_panels = AplansPage.content_panels + [
        FieldPanel('category', widget=CategoryChooser),
        StreamFieldPanel('body'),
    ]

    parent_page_types = [PlanRootPage, EmptyPage, StaticPage, 'CategoryPage']
    subpage_types = [StaticPage, 'CategoryPage']

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLForeignKey('category', Category),
        GraphQLStreamfield('body'),
    ]

    class Meta:
        verbose_name = _('Category page')
        verbose_name_plural = _('Category pages')

    def set_url_path(self, parent):
        path = f'{slugify(self.category.identifier)}-{self.slug}/'
        assert parent is not None
        self.url_path = parent.url_path + path
        return self.url_path
