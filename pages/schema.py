import functools

import graphene
from graphene.types.generic import GenericScalar
from graphene_django.converter import convert_django_field
from wagtail.core.blocks import StaticBlock as WagtailStaticBlock
from wagtail.core.blocks import field_block
from wagtail.core.fields import StreamField as WagtailStreamField
from wagtail.core.models import Page as WagtailPage
from grapple.registry import registry as grapple_registry
from grapple.types.pages import PageInterface

from aplans.graphql_types import DjangoNode
from pages.models import (
    AplansPage, PlanRootPage, CategoryPage, StaticPage as WStaticPage
)
from indicators import blocks as indicators_blocks
from actions import blocks as actions_blocks
from . import blocks as pages_blocks


class MenuItemNode(graphene.ObjectType):
    id = graphene.ID(required=True)
    page = graphene.Field(PageInterface, required=False)
    external_url = graphene.String(required=False)
    link_text = graphene.String(required=True)

    parent = graphene.Field('pages.schema.MenuItemNode')
    children = graphene.List('pages.schema.MenuItemNode')

    def resolve_id(parent, info):
        return parent.page.id

    def resolve_page(parent, info):
        return parent.page.specific

    def resolve_link_text(parent, info):
        return parent.page.title

    def resolve_parent(parent, info):
        parent = WagtailPage.objects.parent_of(parent.page).specific().first()
        if parent is None:
            return
        return MenuItemNode(page=parent)

    def resolve_children(parent, info):
        return [MenuItemNode(page=page) for page in parent.page.get_children().live().public().specific()]


class MenuNodeMixin():
    """
    Mixin for main menu and footer

    You need to provide a `resolve_items(parent, info, with_descendants)` method when you use this mixin.

    It's a mixin instead of a base class because Graphene turns resolver methods into static methods and we can thus
    not use polymorphism in resolver methods.
    https://docs.graphene-python.org/en/latest/types/objecttypes/#resolverimplicitstaticmethod
    """
    items = graphene.List(MenuItemNode, required=True, with_descendants=graphene.Boolean(default_value=False))

    @classmethod
    def resolver_from_plan(cls, plan, info):
        root_page = plan.root_page
        if root_page is None:
            return None
        return root_page.specific

    @classmethod
    def create_plan_menu_field(cls):
        return graphene.Field(cls, resolver=cls.resolver_from_plan)


class MainMenuNode(MenuNodeMixin, graphene.ObjectType):
    def resolve_items(parent, info, with_descendants):
        if not parent:
            return []
        if with_descendants:
            pages = parent.get_descendants(inclusive=False)
        else:
            pages = parent.get_children()
        pages = pages.live().public().in_menu().specific()
        return [MenuItemNode(page=page) for page in pages]


class FooterNode(MenuNodeMixin, graphene.ObjectType):
    def resolve_items(parent, info, with_descendants):
        if not parent:
            return []
        if with_descendants:
            pages = parent.get_descendants(inclusive=False)
        else:
            pages = parent.get_children()
        pages = pages.live().public()
        # AplansPage is abstract and thus has no manager, so we need to find footer pages for each subclass of
        # AplansPage individually. Gather IDs first and then make a separate query for footer_pages because the latter
        # gives us the correct order of the pages.
        footer_page_ids = [page.id
                           for Model in AplansPage.get_subclasses()
                           for page in Model.objects.filter(show_in_footer=True)]
        pages = pages.filter(id__in=footer_page_ids).specific()
        return [MenuItemNode(page=page) for page in pages]
