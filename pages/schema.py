from __future__ import annotations

from typing import TYPE_CHECKING

import graphene
from django.utils.translation import get_language

import graphene_django_optimizer as gql_optimizer
from grapple.types.interfaces import PageInterface
from loguru import logger

from aplans.graphql_types import get_plan_from_context, register_graphene_node

from pages.models import AplansPage

if TYPE_CHECKING:
    from wagtail.models import Page as WagtailPage

    from aplans.cache import PlanSpecificCache
    from aplans.graphql_types import GQLInfo

    from actions.models.plan import Plan


@register_graphene_node
class PageMenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'PageMenuItem'

    id = graphene.ID(required=True)
    page: AplansPage = graphene.Field(PageInterface, required=True)  # type: ignore[assignment]
    parent = graphene.Field('pages.schema.PageMenuItemNode', required=False)
    children = graphene.List(graphene.NonNull('pages.schema.PageMenuItemNode'), required=False)
    cross_plan_link = graphene.Boolean(default_value=False)
    view_url = graphene.String(client_url=graphene.String(required=False), required=False)

    def resolve_id(self, info):
        return self.page.pk

    def get_plan_cache(self, info: GQLInfo) -> PlanSpecificCache:
        plan = get_plan_from_context(info)
        cache = info.context.cache.for_plan(plan)
        return cache

    def resolve_parent(self, info: GQLInfo):
        if not self.page:
            return None
        cache = self.get_plan_cache(info)
        parent = self.page.get_visible_parent(cache)
        if parent is None:
            return None
        return PageMenuItemNode(page=parent)

    def resolve_children(self, info: GQLInfo) -> list[PageMenuItemNode]:
        cache = self.get_plan_cache(info)
        pages = self.page.get_visible_children(cache)

        # TODO: Get rid of this terrible hack
        if 'footer' in info.path.as_list():
            pages = [page for page in pages if page.show_in_footer]
        return [PageMenuItemNode(page=page) for page in pages]

    def resolve_view_url(self, info, client_url=None) -> None | str:
        page = self.page
        plan = page.plan
        if plan is None:
            return None
        if not client_url:
            client_url = info.variable_values.get('clientUrl')
        view_url = plan.get_view_url(client_url=client_url)
        return view_url


@register_graphene_node
class ExternalLinkMenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'ExternalLinkMenuItem'

    id = graphene.ID(required=True)
    url = graphene.String(required=True)
    link_text = graphene.String(required=True)


class MenuItem(graphene.Union):
    class Meta:
        types = (PageMenuItemNode, ExternalLinkMenuItemNode)


class MenuNodeMixin:
    """
    Mixin for main menu and footer.

    You need to provide a `resolve_items(parent, info, with_descendants)` method when you use this mixin.

    It's a mixin instead of a base class because Graphene turns resolver methods into static methods and we can thus
    not use polymorphism in resolver methods.
    https://docs.graphene-python.org/en/latest/types/objecttypes/#resolverimplicitstaticmethod
    """

    items = graphene.List(graphene.NonNull(MenuItem), required=True, with_descendants=graphene.Boolean(default_value=False))

    @staticmethod
    def get_plan_cache_for_page(info: GQLInfo, page: AplansPage) -> PlanSpecificCache:
        plan = get_plan_from_context(info)
        cache = info.context.cache.for_plan(plan)

        root_page = cache.translated_root_page
        assert root_page is not None
        if not page.path.startswith(root_page.path):
            apage = AplansPage.objects.get(path=page.path)
            plan = apage.plan
            if plan is None:
                raise ValueError('Page has no plan')
            cache = info.context.cache.for_plan(plan)
        return cache

    @classmethod
    def resolver_from_plan(cls, plan: Plan, info: GQLInfo) -> None | WagtailPage:
        if not plan.is_visible_for_user(info.context.user):
            return None
        cache = info.context.cache.for_plan(plan)
        return cache.translated_root_page

    @classmethod
    def create_plan_menu_field(cls) -> graphene.Field:
        return graphene.Field(cls, resolver=cls.resolver_from_plan)


class MainMenuNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'MainMenu'

    @staticmethod
    def resolve_items(
        parent: AplansPage | None, info: GQLInfo, with_descendants: bool
    ) -> list[PageMenuItemNode | ExternalLinkMenuItemNode]:
        if not parent:
            return []

        cache = MenuNodeMixin.get_plan_cache_for_page(info, parent)
        if with_descendants:
            pages = parent.get_visible_descendants(cache, in_menu=True)
        else:
            pages = parent.get_visible_children(cache, in_menu=True)
        page_items = [PageMenuItemNode(page=page) for page in pages]
        links = cache.plan.links
        external_link_items = [
            ExternalLinkMenuItemNode(id=str(link.pk), url=link.url_i18n, link_text=link.title_i18n) for link in links.all()
        ]
        return page_items + external_link_items


class FooterNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'Footer'

    @staticmethod
    def resolve_items(parent: AplansPage | None, info: GQLInfo, with_descendants: bool) -> list[PageMenuItemNode]:
        if not parent:
            return []

        cache = MenuNodeMixin.get_plan_cache_for_page(info, parent)
        if with_descendants:
            pages = parent.get_visible_descendants(cache)
        else:
            pages = parent.get_visible_children(cache)
        pages = [page for page in pages if page.show_in_footer]
        return [PageMenuItemNode(page=page) for page in pages]


class AdditionalLinksNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'AdditionalLinks'

    @staticmethod
    def resolve_items(parent: AplansPage | None, info: GQLInfo, with_descendants: bool) -> list[PageMenuItemNode]:
        if not parent:
            return []
        cache = MenuNodeMixin.get_plan_cache_for_page(info, parent)
        if with_descendants:
            pages = parent.get_visible_descendants(cache)
        else:
            pages = parent.get_visible_children(cache)

        pages = [page for page in pages if page.show_in_additional_links]

        # Add general additional links that should be included in all plan pages
        plan = cache.plan
        parent_plan = plan.parent
        if parent_plan is not None and parent_plan.is_visible_for_user(info.context.user):
            parent_plan_cache = info.context.cache.for_plan(parent_plan)
            parent_plan_pages = parent_plan_cache.visible_pages
            cross_plan_pages = [page for page in parent_plan_pages if page.link_in_all_child_plans]
            cross_plan_nodes = [PageMenuItemNode(page=page, cross_plan_link=True) for page in cross_plan_pages]
        else:
            cross_plan_nodes = []
        pages_nodes = [PageMenuItemNode(page=page) for page in pages]
        return pages_nodes + cross_plan_nodes


class Query:
    plan_page = graphene.Field(PageInterface, plan=graphene.ID(required=True), path=graphene.String(required=True))

    def resolve_plan_page(self, info: GQLInfo, plan: str, path: str, **kwargs) -> None | WagtailPage:
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            logger.warning('Plan not found', plan=plan, path=path)
            return None
        if not plan_obj.is_visible_for_user(info.context.user):
            logger.warning('Plan not visible for user', plan=plan, path=path)
            return None

        root = plan_obj.get_translated_root_page()
        if root is None:
            logger.warning('Translated root page not found', plan=plan, locale=get_language())
            return None
        if not path.endswith('/'):
            path = path + '/'
        qs = root.get_descendants(inclusive=True).live().public().filter(url_path=path).specific()
        page = gql_optimizer.query(qs, info).first()
        if page is None:
            logger.warning('Page not found', plan=plan, url_path=path, root_page_name=str(root), root_page_id=root.pk)
        return page
