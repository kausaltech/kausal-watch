import functools
from typing import Optional
from django.contrib.contenttypes.models import ContentType
from django.core.validators import URLValidator
from django.db import models
from django.utils import translation
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from grapple.models import (
    GraphQLBoolean, GraphQLForeignKey, GraphQLImage, GraphQLStreamfield,
    GraphQLString, GraphQLField
)
from modelcluster.fields import ParentalKey
from modeltrans.fields import TranslationField
from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel, StreamFieldPanel
from wagtail.core import blocks
from wagtail.core.fields import RichTextField, StreamField
from wagtail.core.models import Page, Site
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtail.search import index

from actions.blocks import ActionHighlightsBlock, ActionListBlock, CategoryListBlock, RelatedPlanListBlock
from actions.chooser import CategoryChooser
from actions.models import Category, CategoryType, Plan
from indicators.blocks import (
    IndicatorGroupBlock, IndicatorHighlightsBlock, IndicatorShowcaseBlock, RelatedIndicatorsBlock
)
from aplans.utils import OrderedModel
from .blocks import CardListBlock, FrontPageHeroBlock, QuestionAnswerBlock, ActionCategoryFilterCardsBlock


PAGE_TRANSLATED_FIELDS = ['title', 'slug', 'url_path']


class AplansPage(Page):
    i18n = models.JSONField(blank=True, null=True)
    show_in_footer = models.BooleanField(default=False, verbose_name=_('show in footer'),
                                         help_text=_('Should the page be shown in the footer?'),)

    content_panels = [
        FieldPanel('title', classname="full title"),
    ]

    common_settings_panels = [
        FieldPanel('seo_title'),
        FieldPanel('show_in_menus'),
        FieldPanel('show_in_footer'),
        FieldPanel('search_description'),
    ]

    settings_panels = [
        MultiFieldPanel([
            FieldPanel('slug'),
            *common_settings_panels
        ], _('Common page configuration')),
    ]

    search_fields = Page.search_fields + [
        index.FilterField('plan'),
    ]

    promote_panels = []

    graphql_fields = [
        GraphQLField('plan', 'actions.schema.PlanNode', required=False),
        GraphQLBoolean('show_in_footer'),
    ]

    class Meta:
        abstract = True

    @classmethod
    def get_subclasses(cls):
        """Get implementations of this abstract base class"""
        content_types = ContentType.objects.filter(app_label=cls._meta.app_label)
        models = [ct.model_class() for ct in content_types]
        return [model for model in models if (model is not None and issubclass(model, cls) and model is not cls)]

    @functools.cached_property
    def plan(self) -> Optional[Plan]:
        root_page = PlanRootPage.objects.ancestor_of(self, inclusive=True).first()
        site = Site.objects.filter(root_page__translation_key=root_page.translation_key).first()
        plan = Plan.objects.filter(site=site).first()
        return plan

    @classmethod
    def get_indexed_objects(cls):
        # Return only the actions whose plan supports the current language
        lang = translation.get_language()
        qs = super().get_indexed_objects()
        qs = qs.filter(locale__language_code__iexact=lang)
        return qs

    def get_url_parts(self, request=None):
        plan = self.plan
        if not plan:
            return super().get_url_parts(request)

        return (plan.site_id, plan.site_url, self.url_path)


class PlanRootPage(AplansPage):
    hero_content = RichTextField(blank=True, verbose_name=_('hero content'))
    action_short_description = RichTextField(
        blank=True, verbose_name=_('Short description for what actions are')
    )
    indicator_short_description = RichTextField(
        blank=True, verbose_name=_('Short description for what indicators are')
    )

    body = StreamField([
        ('front_page_hero', FrontPageHeroBlock(label=_('Front page hero block'))),
        ('category_list', CategoryListBlock(label=_('Category list'))),
        ('indicator_group', IndicatorGroupBlock()),
        ('indicator_highlights', IndicatorHighlightsBlock(label=_('Indicator highlights'))),
        ('indicator_showcase', IndicatorShowcaseBlock()),
        ('action_highlights', ActionHighlightsBlock(label=_('Action highlights'))),
        ('related_plans', RelatedPlanListBlock(label=_('Related plans'))),
        ('cards', CardListBlock()),
        ('action_links', ActionCategoryFilterCardsBlock(label=_('Links to actions in specific category'))),
    ])

    content_panels = AplansPage.content_panels + [
        FieldPanel('hero_content'),
        FieldPanel('action_short_description'),
        FieldPanel('indicator_short_description'),
        StreamFieldPanel('body'),
    ]

    parent_page_types = []

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLString('action_short_description'),
        GraphQLString('indicator_short_description'),
        GraphQLString('hero_content'),
        GraphQLStreamfield('body'),
    ]

    search_fields = AplansPage.search_fields + [
        index.SearchField('hero_content'),
        index.SearchField('body'),
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
    parent_page_types = [PlanRootPage, 'EmptyPage', 'StaticPage', 'CategoryPage']

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

    parent_page_types = [PlanRootPage, EmptyPage, 'StaticPage', 'CategoryPage']

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLImage('header_image'),
        GraphQLString('lead_paragraph'),
        GraphQLStreamfield('body'),
    ]

    search_fields = AplansPage.search_fields + [
        index.SearchField('lead_paragraph'),
        index.SearchField('body'),
    ]

    class Meta:
        verbose_name = _('Content page')
        verbose_name_plural = _('Content pages')


class CategoryTypePage(StaticPage):
    category_type = models.ForeignKey(
        CategoryType, on_delete=models.PROTECT, null=False, verbose_name=_('Category type'),
        related_name='category_type_pages',
    )


class CategoryPage(AplansPage):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, null=False, verbose_name=_('Category'),
        related_name='category_pages',
    )
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('indicator_group', IndicatorGroupBlock()),
        ('related_indicators', RelatedIndicatorsBlock()),
        ('category_list', CategoryListBlock(label=_('Category list'))),
        ('action_list', ActionListBlock(label=_('Action list')))
    ], null=True, blank=True)

    # Omit title field -- should be edited in CategoryAdmin
    inherited_content_panels = [p for p in AplansPage.content_panels if p.field_name != 'title']
    content_panels = inherited_content_panels + [
        FieldPanel('category', widget=CategoryChooser),
        StreamFieldPanel('body'),
    ]

    parent_page_types = [PlanRootPage, EmptyPage, StaticPage, 'CategoryPage']
    subpage_types = [StaticPage, 'CategoryPage']

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLForeignKey('category', Category),
        GraphQLStreamfield('body'),
    ]

    search_fields = AplansPage.search_fields + [
        index.FilterField('category'),
        index.SearchField('body'),
    ]

    class Meta:
        verbose_name = _('Category page')
        verbose_name_plural = _('Category pages')

    def set_url_path(self, parent):
        path = f'{slugify(self.category.identifier)}-{self.slug}/'
        assert parent is not None
        self.url_path = parent.url_path + path
        return self.url_path


class FixedSlugPage(AplansPage):
    """
    Page with fixed slug

    Define `force_slug` in the body of subclasses.

    Since the slug is fixed, there can be at most one child page of the respective type.
    """
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        kwargs['slug'] = self.__class__.force_slug
        super().__init__(*args, **kwargs)

    remove_page_listing_more_button = True
    remove_page_action_menu_items_except_publish = True

    lead_content = RichTextField(blank=True, verbose_name=_('lead content'))

    # Omit the title from the editable fields
    inherited_content_panels = [p for p in AplansPage.content_panels if p.field_name != 'title']
    content_panels = inherited_content_panels + [
        FieldPanel('title'),
        FieldPanel('lead_content'),
    ]
    settings_panels = [
        MultiFieldPanel(
            AplansPage.common_settings_panels,
            _('Common page configuration')
        ),
    ]

    # Only let this be created programmatically
    parent_page_types = []
    subpage_types = []

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLString('lead_content'),
    ]


class ActionListPage(FixedSlugPage):
    force_slug = 'actions'


class IndicatorListPage(FixedSlugPage):
    force_slug = 'indicators'


class ImpactGroupPage(FixedSlugPage):
    force_slug = 'impact-groups'


class PlanLink(OrderedModel):
    """A link related to a plan."""

    plan = ParentalKey(Plan, on_delete=models.CASCADE, verbose_name=_('plan'), related_name='links')
    url = models.URLField(max_length=400, verbose_name=_('URL'), validators=[URLValidator(('http', 'https'))])
    title = models.CharField(max_length=254, verbose_name=_('title'), blank=True)

    public_fields = [
        'id', 'plan', 'url', 'title', 'order'
    ]

    i18n = TranslationField(
        fields=['title', 'url'],
        default_language_field='plan__primary_language',
    )

    class Meta:
        ordering = ['plan', 'order']
        index_together = (('plan', 'order'),)
        verbose_name = _('external plan link')
        verbose_name_plural = _('external plan links')

    def __str__(self):
        if self.title:
            return f'{self.title}: {self.url}'
        return self.url
