import functools
from typing import ClassVar, Optional, Sequence, Type
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, MinValueValidator
from django.db import models
from django.utils import translation
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
import graphene
from grapple.models import (
    GraphQLBoolean, GraphQLForeignKey, GraphQLImage, GraphQLStreamfield,
    GraphQLInt, GraphQLString, GraphQLField
)
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail import blocks
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, Panel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page, PagePermissionTester, Site
from wagtail.search import index

from actions.blocks import (
    ActionHighlightsBlock, ActionListBlock, ActionListFilterBlock, CategoryListBlock, CategoryTreeMapBlock,
    RelatedPlanListBlock, ActionAsideContentBlock, ActionMainContentBlock, get_default_action_content_blocks,
    get_default_action_filter_blocks
)
from actions.blocks.action_dashboard import ActionDashboardColumnBlock
from actions.blocks.category_page_layout import (
    CategoryPageMainBottomBlock, CategoryPageMainTopBlock, CategoryPageAsideBlock
)
from actions.chooser import CategoryChooser, CategoryLevelChooser, CategoryTypeChooser
from actions.models.category import Category, CategoryType
from actions.models.plan import Plan
from aplans.extensions import get_body_blocks
from indicators.blocks import (
    IndicatorGroupBlock, IndicatorHighlightsBlock, IndicatorShowcaseBlock, RelatedIndicatorsBlock
)
from aplans.utils import OrderedModel, DateFormatField, DateFormatOptions
from .blocks import (
    AccessibilityStatementComplianceStatusBlock, AccessibilityStatementContactInformationBlock,
    AccessibilityStatementContactFormBlock, AccessibilityStatementPreparationInformationBlock, CardListBlock,
    FrontPageHeroBlock, QuestionAnswerBlock, ActionCategoryFilterCardsBlock,
    ActionStatusGraphsBlock, AdaptiveEmbedBlock, LargeImageBlock
)


PAGE_TRANSLATED_FIELDS = ['title', 'slug', 'url_path']


class AplansPage(Page):
    i18n = models.JSONField(blank=True, null=True)
    show_in_footer = models.BooleanField(default=False, verbose_name=_('show in footer'),
                                         help_text=_('Should the page be shown in the footer?'),)
    show_in_additional_links = models.BooleanField(default=False, verbose_name=_('show in additional links'),
                                                   help_text=_('Should the page be shown in the additional links?'),)
    children_use_secondary_navigation = models.BooleanField(
        default=False, verbose_name=_('children use secondary navigation'),
        help_text=_('Should subpages of this page use secondary navigation?')
    )

    content_panels = [
        FieldPanel('title', classname="full title"),
    ]

    common_settings_panels = [
        FieldPanel('seo_title'),
        FieldPanel('show_in_menus'),
        FieldPanel('show_in_footer'),
        FieldPanel('show_in_additional_links'),
        FieldPanel('children_use_secondary_navigation'),
        FieldPanel('search_description'),
    ]

    settings_panels = [
        *Page.settings_panels,
        MultiFieldPanel([
            FieldPanel('slug'),
            *common_settings_panels
        ], _('Common page configuration')),
    ]

    search_fields = Page.search_fields + [
        index.FilterField('plan'),
    ]

    promote_panels: list[Panel] = []

    graphql_fields = [
        GraphQLField('plan', 'actions.schema.PlanNode', required=False),
        GraphQLBoolean('show_in_footer'),
        GraphQLBoolean('show_in_additional_links'),
        GraphQLBoolean('children_use_secondary_navigation'),
    ]

    class Meta:
        abstract = True

    @property
    def preview_modes(self):
        return []

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
        qs = qs.filter(locale__language_code__istartswith=lang)
        return qs

    def get_url_parts(self, request=None):
        plan = self.plan
        if not plan:
            return super().get_url_parts(request)

        return (plan.site_id, plan.site_url, self.url_path)


class PlanRootPage(AplansPage):
    body = StreamField([
        ('front_page_hero', FrontPageHeroBlock()),
        ('category_list', CategoryListBlock()),
        ('indicator_group', IndicatorGroupBlock()),
        ('indicator_highlights', IndicatorHighlightsBlock()),
        ('indicator_showcase', IndicatorShowcaseBlock()),
        ('action_highlights', ActionHighlightsBlock()),
        ('related_plans', RelatedPlanListBlock()),
        ('cards', CardListBlock()),
        ('action_links', ActionCategoryFilterCardsBlock(label=_('Links to actions in specific category'))),
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('action_status_graphs', ActionStatusGraphsBlock()),
        ('category_tree_map', CategoryTreeMapBlock()),
        ('large_image', LargeImageBlock()),
        ('embed', AdaptiveEmbedBlock()),
    ], use_json_field=True)

    content_panels = [
        FieldPanel('body'),
    ]

    parent_page_types: Sequence[Type[Page] | str] = []

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLStreamfield('body'),
    ]

    search_fields = AplansPage.search_fields + [
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
        ('paragraph', blocks.RichTextBlock(label=_('Paragraph'))),
        ('qa_section', QuestionAnswerBlock(icon='help')),
        ('category_list', CategoryListBlock()),
        ('embed', AdaptiveEmbedBlock()),
        ('category_tree_map', CategoryTreeMapBlock()),
        ('large_image', LargeImageBlock()),
        *get_body_blocks('StaticPage')
    ], null=True, blank=True, use_json_field=True)

    content_panels = AplansPage.content_panels + [
        FieldPanel('header_image'),
        FieldPanel('lead_paragraph'),
        FieldPanel('body'),
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


class ReadOnlyFieldPanelWithRawValueId(FieldPanel):
    """Variant of FieldPanel where `raw_value.id` is added as a hidden <input> element to be used by JS code."""
    def __init__(self, *args, **kwargs):
        kwargs['read_only'] = True
        super().__init__(*args, **kwargs)

    read_only_output_template_name = "aplans/panels/read_only_output_with_raw_value_id.html"


class CategoryTypeRelatedPagePermissionTester(PagePermissionTester):
    def __init__(self, user, page, category_type):
        super().__init__(user, page)
        self.category_type = category_type

    def can_add_subpage(self):
        return super().can_add_subpage() and not self.category_type.synchronize_with_pages

    def can_delete(self, ignore_bulk=False):
        return super().can_delete(ignore_bulk) and not self.category_type.synchronize_with_pages

    def can_reorder_children(self):
        return super().can_reorder_children() and not self.category_type.synchronize_with_pages

    def can_move(self):
        return super().can_move() and not self.category_type.synchronize_with_pages

    def can_copy(self):
        return super().can_copy() and not self.category_type.synchronize_with_pages


class CategoryTypePagePermissionTester(CategoryTypeRelatedPagePermissionTester):
    def __init__(self, user, page):
        super().__init__(user, page, page.category_type)


class CategoryPagePermissionTester(CategoryTypeRelatedPagePermissionTester):
    def __init__(self, user, page):
        super().__init__(user, page, page.category.type)


class CategoryTypePage(StaticPage):
    category_type = models.ForeignKey(
        CategoryType, on_delete=models.CASCADE, null=False, verbose_name=_('Category type'),
        related_name='category_type_pages',
    )

    content_panels = StaticPage.content_panels + [
        # We use a version of FieldPanel with a hacked read-only template to provide the ID of the selected category
        # type as a hidden <input> element.
        ReadOnlyFieldPanelWithRawValueId('category_type', widget=CategoryTypeChooser),
        InlinePanel('level_layouts', heading=_('Level layouts'), panels=[
            FieldPanel('level', widget=CategoryLevelChooser(linked_fields={
                # ID of the hidden <input> element with the category type ID
                'type': '#panel-child-content-child-category_type-raw-value-id',
            })),
            FieldPanel('layout_main_top'),
            FieldPanel('layout_main_bottom'),
            FieldPanel('layout_aside'),
            FieldPanel('icon_size'),
        ]),
    ]

    class Meta:
        verbose_name = _('Category type page')
        verbose_name_plural = _('Category type pages')

    @property
    def remove_sort_menu_order_button(self):
        return self.category_type.synchronize_with_pages

    def permissions_for_user(self, user):
        return CategoryTypePagePermissionTester(user, self)


# FIXME: Duplicated code (see action_list_page_streamfield_node_getter)
def category_type_page_level_layout_streamfield_node_getter(field_name):
    def get_node() -> GraphQLField:
        from grapple.registry import registry

        field = CategoryTypePageLevelLayout._meta.get_field(field_name)
        assert isinstance(field, StreamField)
        node = registry.streamfield_blocks[type(field.stream_block)]
        field_type = graphene.List(graphene.NonNull(node))
        return GraphQLField(field_name, field_type, required=False)  # type: ignore

    return get_node


class CategoryTypePageLevelLayout(ClusterableModel):
    class IconSize(models.TextChoices):
        SMALL = 'S', _('Small')
        MEDIUM = 'M', _('Medium')
        LARGE = 'L', _('Large')

    page = ParentalKey(
        CategoryTypePage, on_delete=models.CASCADE, related_name='level_layouts', verbose_name=('page')
    )
    level = models.ForeignKey(
        'actions.CategoryLevel', on_delete=models.CASCADE, related_name='level_layouts',
        null=True, blank=True, verbose_name=_('level')
    )
    layout_main_top = StreamField(
        block_types=CategoryPageMainTopBlock(), null=True, blank=True, use_json_field=True,
        verbose_name=_('layout main top')
    )
    layout_main_bottom = StreamField(
        block_types=CategoryPageMainBottomBlock(), null=True, blank=True, use_json_field=True,
        verbose_name=_('layout main bottom')
    )
    layout_aside = StreamField(
        block_types=CategoryPageAsideBlock(), null=True, blank=True, use_json_field=True,
        verbose_name=_('layout aside')
    )
    icon_size = models.CharField(
        max_length=4, choices=IconSize.choices, default=IconSize.MEDIUM, verbose_name=_('icon size')
    )

    graphql_fields = [
        category_type_page_level_layout_streamfield_node_getter('layout_main_top'),
        category_type_page_level_layout_streamfield_node_getter('layout_main_bottom'),
        category_type_page_level_layout_streamfield_node_getter('layout_aside'),
        GraphQLString('icon_size'),
    ]

    class Meta:
        unique_together = (('page', 'level'),)

    def clean(self) -> None:
        super().clean()
        # FIXME: There is no page since it's a clusterable model
        # category_type = self.page.category_type
        # if self.level is not None and self.level not in category_type.levels.all():
        #     raise ValidationError({'level': "Invalid level"})


class CategoryPage(AplansPage):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, null=False, verbose_name=_('Category'),
        related_name='category_pages',
    )
    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('qa_section', QuestionAnswerBlock(icon='help')),
        ('indicator_group', IndicatorGroupBlock()),
        ('related_indicators', RelatedIndicatorsBlock()),
        ('category_list', CategoryListBlock()),
        ('action_list', ActionListBlock()),
        ('embed', AdaptiveEmbedBlock()),
    ], null=True, blank=True, use_json_field=True)

    content_panels = AplansPage.content_panels + [
        FieldPanel('category', widget=CategoryChooser, read_only=True),
        FieldPanel('body'),
    ]

    parent_page_types = [PlanRootPage, EmptyPage, StaticPage, 'CategoryPage', 'CategoryTypePage']
    subpage_types = [StaticPage, 'CategoryPage']

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLForeignKey('category', Category),
        GraphQLStreamfield('body'),
        GraphQLForeignKey('layout', CategoryTypePageLevelLayout),
    ]

    search_fields = AplansPage.search_fields + [
        index.FilterField('category'),
        index.SearchField('body'),
    ]

    class Meta:
        verbose_name = _('Category page')
        verbose_name_plural = _('Category pages')

    def set_url_path(self, parent: Page):
        if self.category.type.hide_category_identifiers:
            path = f'{self.slug}/'
        else:
            path = f'{slugify(self.category.identifier)}-{self.slug}/'
        assert parent is not None
        self.url_path = parent.url_path + path
        return self.url_path

    def validate_unique(self, exclude=None):
        # This can't be a constraint on the DB level because `locale` and `category` are in different tables
        super().validate_unique(exclude)
        qs = CategoryPage.objects.filter(category=self.category, locale=self.locale)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({
                'category': _('This category already has a page')
            })

    def get_layout(self) -> Optional[CategoryTypePageLevelLayout]:
        type_page = self.get_ancestors().type(CategoryTypePage).specific().last()
        if not type_page:
            return None
        # First try to get layout for the specific level; if this fails, get layout where `level` is NULL
        level = self.category.get_level()
        if level:
            try:
                return type_page.level_layouts.get(level=level)
            except CategoryTypePageLevelLayout.DoesNotExist:
                pass
        try:
            return type_page.level_layouts.get(level__isnull=True)
        except CategoryTypePageLevelLayout.DoesNotExist:
            return None

    # FIXME
    @property
    def layout(self):
        return self.get_layout()

    def permissions_for_user(self, user):
        return CategoryPagePermissionTester(user, self)


class FixedSlugPage(AplansPage):
    """
    Page with fixed slug

    Define `force_slug` in the body of subclasses. You may also want to set is_creatable to False there to allow only
    programmatic creation.

    Since the slug is fixed, there can be at most one child page of the respective type.
    """
    force_slug: ClassVar[str]

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.slug:  # type: ignore[has-type]
            self.slug = self.__class__.force_slug

    restrict_more_button_permissions_very_much = True
    remove_page_action_menu_items_except_publish = True

    lead_content = RichTextField(blank=True, verbose_name=_('lead content'))

    content_panels = AplansPage.content_panels + [
        FieldPanel('lead_content'),
    ]
    settings_panels = [
        MultiFieldPanel(
            AplansPage.common_settings_panels,
            _('Common page configuration')
        ),
    ]

    graphql_fields = AplansPage.graphql_fields + [
        GraphQLString('lead_content'),
    ]


def action_list_page_streamfield_node_getter(field_name):
    def get_node() -> GraphQLField:
        from grapple.registry import registry

        field = ActionListPage._meta.get_field(field_name)
        assert isinstance(field, StreamField)
        node = registry.streamfield_blocks[type(field.stream_block)]
        field_type = graphene.List(graphene.NonNull(node))
        return GraphQLField(field_name, field_type, required=False)  # type: ignore

    return get_node


# Adapted from graphene.types.enum.EnumMeta.from_enum() because the original doesn't let us change the name. So the type
# created for ActionListPage.View would be called "View" instead of the more reasonable "ActionListPageView".
def graphql_type_from_enum(enum, name=None):
    meta_dict = {
        "enum": enum,
        "name": name,
        "description": None,
        "deprecation_reason": None,
    }
    meta_class = type("Meta", (object,), meta_dict)
    return type(meta_class.enum.__name__, (graphene.types.Enum,), {"Meta": meta_class})  # type: ignore[attr-defined]


class ActionListPage(FixedSlugPage):
    class View(models.TextChoices):
        CARDS = 'cards', _('Cards')
        DASHBOARD = 'dashboard', _('Dashboard')

    primary_filters = StreamField(block_types=ActionListFilterBlock(), null=True, blank=True, use_json_field=True)
    main_filters = StreamField(block_types=ActionListFilterBlock(), null=True, blank=True, use_json_field=True)
    advanced_filters = StreamField(block_types=ActionListFilterBlock(), null=True, blank=True, use_json_field=True)

    dashboard_columns = StreamField(block_types=ActionDashboardColumnBlock(), null=True, blank=True, use_json_field=True)

    details_main_top = StreamField(block_types=ActionMainContentBlock(), null=True, blank=True, use_json_field=True)
    details_main_bottom = StreamField(block_types=ActionMainContentBlock(), null=True, blank=True, use_json_field=True)
    details_aside = StreamField(block_types=ActionAsideContentBlock(), null=True, blank=True, use_json_field=True)

    card_icon_category_type = models.ForeignKey(
        CategoryType, on_delete=models.SET_NULL, null=True, blank=True
    )
    default_view = models.CharField(
        max_length=30, choices=View.choices, default=View.CARDS, verbose_name=_('default view'),
        help_text=_("Tab of the action list page that should be visible by default")
    )
    heading_hierarchy_depth = models.IntegerField(
        verbose_name=_('Subheading hierarchy depth'),
        help_text=_('Depth of category hierarchy to present as subheadings starting from the root.'),
        validators=(MinValueValidator(1),),
        default=1
    )
    action_date_format = DateFormatField(
        verbose_name=_('Action date format'),
        help_text=_('Default format of action start and end dates shown in the public UI.'),
        default=DateFormatOptions.FULL
    )
    task_date_format = DateFormatField(
        verbose_name=_('Task due date format'),
        help_text=_('Default format of action task due dates shown in the public UI.'),
        default=DateFormatOptions.FULL
    )
    include_related_plans = models.BooleanField(
        verbose_name=_('Include related plans'),
        help_text=_('Enable to make this page include actions from related plans.'),
        default=False
    )

    force_slug = 'actions'
    is_creatable = False  # Only let this be created programmatically

    parent_page_type = [PlanRootPage]

    content_panels = FixedSlugPage.content_panels + [
        FieldPanel('default_view'),
        FieldPanel('heading_hierarchy_depth'),
        FieldPanel('include_related_plans'),
        FieldPanel('action_date_format'),
        FieldPanel('task_date_format'),
        MultiFieldPanel([
            FieldPanel('primary_filters', heading=_("Primary filters")),
            FieldPanel('main_filters', heading=_("Main filters")),
            FieldPanel('advanced_filters', heading=_("Advanced filters (hidden by default)")),
        ], heading=_("Action list filters"), classname="collapsible collapsed"),
        MultiFieldPanel([
            FieldPanel('details_main_top', heading=_("Main column (top part on mobile)")),
            FieldPanel('details_main_bottom', heading=_("Main column (bottom part on mobile)")),
            FieldPanel('details_aside', heading=_("Side column")),
        ], heading=_("Action details page"), classname="collapsible collapsed"),
        FieldPanel('dashboard_columns', heading=_("Action dashboard columns"), classname="collapsible collapsed"),
    ]

    graphql_fields = FixedSlugPage.graphql_fields + [
        # Graphene / grapple don't allow us to easily add default_view here. If we added
        # GraphQLField('default_view', graphene.Enum.from_enum(View), required=True),
        # then the type would be called `View`, not `ActionListPageView`, as the automatically generated type is.
        GraphQLField('default_view', graphql_type_from_enum(View, 'ActionListPageView'), required=True),
        GraphQLInt(field_name='heading_hierarchy_depth', required=True),
        GraphQLBoolean('include_related_plans'),
        GraphQLString('action_date_format'),
        GraphQLString('task_date_format'),
        action_list_page_streamfield_node_getter('primary_filters'),
        action_list_page_streamfield_node_getter('main_filters'),
        action_list_page_streamfield_node_getter('advanced_filters'),
        action_list_page_streamfield_node_getter('details_main_top'),
        action_list_page_streamfield_node_getter('details_main_bottom'),
        action_list_page_streamfield_node_getter('details_aside'),
        action_list_page_streamfield_node_getter('dashboard_columns'),
    ]

    def set_default_content_blocks(self):
        plan: Plan = self.get_site().plan

        blks = get_default_action_content_blocks(plan)
        for key, val in blks.items():
            assert self._meta.get_field(key)
            setattr(self, key, val)

        blks = get_default_action_filter_blocks(plan)
        for key, val in blks.items():
            assert self._meta.get_field(key)
            setattr(self, key, val)

        self.save()

    def contains_model_instance_block(self, instance, field_name):
        field = getattr(self, field_name)
        return field.stream_block.contains_model_instance(instance, field)

    def insert_model_instance_block(self, instance, field_name):
        field = getattr(self, field_name)
        return field.stream_block.insert_model_instance(instance, field)

    def remove_model_instance_block(self, instance, field_name):
        field = getattr(self, field_name)
        return field.stream_block.remove_model_instance(instance, field)

    class Meta:
        verbose_name = _('Action list page')
        verbose_name_plural = _('Action list pages')


class IndicatorListPage(FixedSlugPage):
    force_slug = 'indicators'
    is_creatable = False  # Only let this be created programmatically
    parent_page_type = [PlanRootPage]

    display_insights = models.BooleanField(
        default=True,
        help_text=_('Should insight network be shown for indicators?'),
        verbose_name=_('Display insights')
    )

    content_panels = FixedSlugPage.content_panels + [
        FieldPanel('display_insights')
    ]

    graphql_fields = FixedSlugPage.graphql_fields + [
        GraphQLBoolean('display_insights')
    ]

    class Meta:
        verbose_name = _('Indicator list page')
        verbose_name_plural = _('Indicator list pages')


class ImpactGroupPage(FixedSlugPage):
    force_slug = 'impact-groups'
    is_creatable = False  # Only let this be created programmatically
    parent_page_type = [PlanRootPage]

    class Meta:
        verbose_name = _('Impact group page')
        verbose_name_plural = _('Impact group pages')


class PrivacyPolicyPage(FixedSlugPage):
    force_slug = 'privacy'
    is_creatable = False  # Only let this be created programmatically
    parent_page_type = [PlanRootPage]

    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        # TODO: What blocks do we want to offer here (cf. AccessibilityStatementPage)?
    ], null=True, blank=True, use_json_field=True)

    class Meta:
        verbose_name = _('Privacy policy page')
        verbose_name_plural = _('Privacy policy pages')


class AccessibilityStatementPage(FixedSlugPage):
    force_slug = 'accessibility'
    is_creatable = False  # Only let this be created programmatically
    parent_page_type = [PlanRootPage]

    body = StreamField([
        ('text', blocks.RichTextBlock(label=_('Text'))),
        ('compliance_status', AccessibilityStatementComplianceStatusBlock()),
        ('preparation', AccessibilityStatementPreparationInformationBlock()),
        ('contact_information', AccessibilityStatementContactInformationBlock()),
        ('contact_form', AccessibilityStatementContactFormBlock()),
    ], null=True, blank=True, use_json_field=True)

    content_panels = FixedSlugPage.content_panels + [
        FieldPanel('body'),
    ]

    graphql_fields = FixedSlugPage.graphql_fields + [
        GraphQLStreamfield('body'),
    ]

    class Meta:
        verbose_name = _('Accessibility statement page')
        verbose_name_plural = _('Accessibility statement pages')


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
        default_language_field='plan__primary_language_lowercase',
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
