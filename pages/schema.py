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

    def resolve_id(self, info):
        return self.page.id

    def resolve_page(self, info):
        return self.page.specific

    def resolve_link_text(self, info):
        return self.page.title

    def resolve_parent(self, info):
        parent = WagtailPage.objects.parent_of(self.page).specific().first()
        if parent is None:
            return
        return MenuItemNode(page=parent)

    def resolve_children(self, info):
        return [MenuItemNode(page) for page in self.page.get_children().live().public().specific()]


class MenuNode(graphene.ObjectType):
    items = graphene.List(MenuItemNode, required=True, with_descendants=graphene.Boolean(default_value=False))

    @classmethod
    def resolve_from_plan(cls, plan, info):
        root_page = plan.root_page
        if root_page is None:
            return None
        return root_page.specific

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
        pages = pages.live().public().in_menu().specific()
        return [MenuNode.menu_item_from_page(page) for page in pages]

    @classmethod
    def create_plan_menu_field(cls):
        return graphene.Field(cls, resolver=cls.resolve_from_plan)


class FooterNode(graphene.ObjectType):
    items = graphene.List(MenuItemNode, required=True)

    @classmethod
    def resolve_from_plan(cls, plan, info):
        root_page = plan.root_page
        if root_page is None:
            return None
        return root_page.specific

    @classmethod
    def footer_item_from_page(self, page):
        return MenuItemNode(page=page)

    def resolve_items(self, info):
        if not self:
            return []

        # AplansPage is abstract and thus has no manager, so we need to find footer pages for each subclass of
        # AplansPage individually. Gather IDs first and then make a separate query for footer_pages because the latter
        # gives us the correct order of the pages.
        footer_page_ids = [page.id
                           for Model in AplansPage.get_subclasses()
                           for page in Model.objects.filter(show_in_footer=True).child_of(self).live().public()]
        footer_pages = WagtailPage.objects.filter(id__in=footer_page_ids).specific()
        return [FooterNode.footer_item_from_page(page) for page in footer_pages]

    @classmethod
    def create_plan_footer_field(cls):
        return graphene.Field(cls, resolver=cls.resolve_from_plan)
