import functools

import graphene
from graphene.types.generic import GenericScalar
from graphene_django.converter import convert_django_field
from wagtail.core.blocks import StaticBlock as WagtailStaticBlock
from wagtail.core.blocks import field_block
from wagtail.core.fields import StreamField as WagtailStreamField
from wagtail.core.models import Page as WagtailPage

from aplans.graphql_types import DjangoNode
from pages.models import (
    AplansPage, PlanRootPage, CategoryPage, StaticPage as WStaticPage
)
from indicators import blocks as indicators_blocks
from actions import blocks as actions_blocks
from . import blocks as pages_blocks

BASE_PAGE_FIELDS = [
    'id', 'slug', 'title', 'url_path',
]


class Page(graphene.Interface):
    id = graphene.ID(required=True)
    title = graphene.String(required=True)
    slug = graphene.String(required=True)
    url_path = graphene.String(required=True)
    parent = graphene.Field('pages.schema.Page')

    def resolve_url_path(self, info):
        url_path = self.url_path.strip('/')
        parts = url_path.split('/')
        parts[0] = ''
        return '/'.join(parts)


class BasePageNode(DjangoNode):
    def resolve_parent(self, info):
        if isinstance(self, PlanRootPage):
            return None

        return self.get_parent()

    class Meta:
        abstract = True


class StreamFieldBlock(graphene.Interface):
    id = graphene.ID(required=True)
    name = graphene.String(required=True)

    @classmethod
    def resolve_type(cls, instance, info):
        type_class = None
        if isinstance(instance.block, field_block.CharBlock):
            type_class = CharBlock
        elif isinstance(instance.block, field_block.RichTextBlock):
            type_class = RichTextBlock
        elif isinstance(instance.block, field_block.ChoiceBlock):
            type_class = CharBlock
        elif isinstance(instance.block, WagtailStaticBlock):
            type_class = StaticBlock
        elif isinstance(instance.block, pages_blocks.QuestionAnswerBlock):
            type_class = QuestionAnswerBlock
        elif isinstance(instance.block, pages_blocks.FrontPageHeroBlock):
            type_class = FrontPageHeroBlock
        elif isinstance(instance.block, indicators_blocks.IndicatorBlock):
            type_class = IndicatorBlock
        elif isinstance(instance.block, indicators_blocks.IndicatorHighlightsBlock):
            type_class = IndicatorHighlightsBlock
        elif isinstance(instance.block, actions_blocks.CategoryListBlock):
            type_class = CategoryListBlock
        elif isinstance(instance.block, actions_blocks.ActionListBlock):
            type_class = ActionListBlock
        else:
            raise Exception('Unknown type: %s' % instance.block)

        # Fill in the data from the 'value' attribute
        if hasattr(instance.value, 'items'):
            for key, value in instance.value.items():
                setattr(instance, key, value)

        return type_class

    def resolve_name(self, info):
        return self.block.name


class RichTextBlock(graphene.ObjectType):
    value = graphene.String(required=True)

    def resolve_value(self, info):
        return str(self)

    class Meta:
        interfaces = (StreamFieldBlock,)


class StaticBlock(graphene.ObjectType):
    class Meta:
        interfaces = (StreamFieldBlock,)


class CharBlock(graphene.ObjectType):
    value = graphene.String(required=True)

    class Meta:
        interfaces = (StreamFieldBlock,)


class IndicatorBlock(graphene.ObjectType):
    indicator = graphene.Field('indicators.schema.IndicatorNode', required=True)
    style = graphene.Field(CharBlock, required=True)

    class Meta:
        interfaces = (StreamFieldBlock,)


class ActionListBlock(graphene.ObjectType):
    category_filter = graphene.Field('aplans.schema.CategoryNode', required=False)

    class Meta:
        interfaces = (StreamFieldBlock,)


class CategoryListBlock(graphene.ObjectType):
    style = graphene.Field(CharBlock, required=True)

    class Meta:
        interfaces = (StreamFieldBlock,)


class StructBlock(graphene.ObjectType):
    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs):
        def resolve_field(field_name, obj, info):
            ret = obj.value[field_name]
            return ret

        kwargs['interfaces'] = (StreamFieldBlock,)
        super().__init_subclass_with_meta__(**kwargs)

        for field_name, field in cls._meta.fields.items():
            if field_name in ('id', 'name'):
                continue
            field.resolver = functools.partial(resolve_field, field_name)

    class Meta:
        # interfaces = (StreamFieldBlock,)
        abstract = True


class QuestionAnswer(graphene.ObjectType):
    question = graphene.String(required=True)
    answer = graphene.String(required=True)


class QuestionAnswerBlock(StructBlock):
    heading = graphene.String(required=True)
    questions = graphene.List(QuestionAnswer)


class FrontPageHeroBlock(StructBlock):
    layout = graphene.String(required=True)
    image = graphene.Field('images.schema.ImageNode')
    heading = graphene.String(required=True)
    lead = graphene.String(required=True)


class StreamField(graphene.ObjectType):
    blocks = graphene.List(StreamFieldBlock)

    def resolve_blocks(self, info):
        return list(self)


@convert_django_field.register(WagtailStreamField)
def convert_stream_field(field, registry=None):
    return graphene.Field(StreamField, description=field.help_text, required=not field.null)


class WStaticPageNode(BasePageNode):
    class Meta:
        model = WStaticPage
        only_fields = BASE_PAGE_FIELDS + ['header_image', 'lead_paragraph', 'body']
        interfaces = (Page,)


class CategoryPageNode(BasePageNode):
    class Meta:
        model = CategoryPage
        only_fields = BASE_PAGE_FIELDS + ['category', 'body']
        interfaces = (Page,)


class RootPageNode(BasePageNode):
    class Meta:
        model = PlanRootPage
        only_fields = BASE_PAGE_FIELDS + ['body']
        interfaces = (Page,)


class MenuItemNode(graphene.ObjectType):
    id = graphene.ID(required=True)
    page = graphene.Field(Page, required=False)
    external_url = graphene.String(required=False)
    link_text = graphene.String(required=True)

    parent = graphene.Field('pages.schema.MenuItemNode')
    children = graphene.List('pages.schema.MenuItemNode')

    def resolve_id(self, info):
        return self.page.id

    def resolve_page(self, info):
        return self.page

    def resolve_link_text(self, info):
        return self.page.title

    def resolve_parent(self, info):
        parent = WagtailPage.objects.parent_of(self.page).specific().first()
        if parent is None:
            return
        return MenuItemNode(page=parent)

    def resolve_children(self, info):
        return [MenuItemNode(page) for page in self.page.get_children().specific()]


class MenuNode(graphene.ObjectType):
    items = graphene.List(MenuItemNode, required=True, with_descendants=graphene.Boolean(default_value=False))

    @classmethod
    def resolve_from_plan(cls, plan, info):
        root_page = plan.root_page
        if root_page is None:
            return None
        return root_page

    @classmethod
    def menu_item_from_page(self, page):
        return MenuItemNode(page=page)

    def resolve_items(self, info, with_descendants):
        if not self:
            return []
        if with_descendants:
            pages = self.get_descendants(inclusive=False)
        else:
            pages = self.get_children()
        pages = pages.specific()
        return [MenuNode.menu_item_from_page(page) for page in pages]

    @classmethod
    def create_plan_menu_field(cls):
        return graphene.Field(cls, resolver=cls.resolve_from_plan)


types = [
    WStaticPageNode, RootPageNode, CategoryPageNode,
    CharBlock, StaticBlock, QuestionAnswerBlock, RichTextBlock, FrontPageHeroBlock,
    CategoryListBlock, ActionListBlock, IndicatorBlock,
]
