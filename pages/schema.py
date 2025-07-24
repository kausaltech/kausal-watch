from __future__ import annotations

from typing import TYPE_CHECKING

import graphene
from wagtail.models import Page as WagtailPage

import graphene_django_optimizer as gql_optimizer
from grapple.types.interfaces import PageInterface

from aplans.graphql_types import get_plan_from_context, register_graphene_node

from pages.models import AplansPage

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo

    from actions.models.plan import Plan


@register_graphene_node
class PageMenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'PageMenuItem'

    id = graphene.ID(required=True)
    page: AplansPage = graphene.Field(PageInterface, required=True)  # type: ignore[assignment]
    parent = graphene.Field('pages.schema.PageMenuItemNode')
    children = graphene.List('pages.schema.PageMenuItemNode')
    cross_plan_link = graphene.Boolean()
    view_url = graphene.String(client_url=graphene.String(required=False))

    def resolve_id(self, info):
        return self.page.pk

    def resolve_parent(self, info):
        if not self.page:
            return None
        parent = WagtailPage.objects.get_queryset().parent_of(self.page).specific().first()
        if parent is None:
            return None
        return PageMenuItemNode(page=parent)

    def resolve_children(self, info: GQLInfo) -> list[PageMenuItemNode]:
        pages = self.page.get_children().live().public()
        # TODO: Get rid of this terrible hack
        if 'footer' in info.path.as_list():
            footer_page_ids = [page.pk
                               for Model in AplansPage.get_subclasses()
                               for page in Model.objects.filter(show_in_footer=True)]
            pages = pages.filter(id__in=footer_page_ids)
        pages = pages.specific()
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

    items = graphene.List(MenuItem, required=True, with_descendants=graphene.Boolean(default_value=False))

    @classmethod
    def resolver_from_plan(cls, plan: Plan, info: GQLInfo) -> None | WagtailPage:
        root_page = plan.get_translated_root_page()
        if not plan.is_visible_for_user(info.context.user):
            return None
        if root_page is None:
            return None
        return root_page.specific

    @classmethod
    def create_plan_menu_field(cls) -> graphene.Field:
        return graphene.Field(cls, resolver=cls.resolver_from_plan)


class MainMenuNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'MainMenu'

    @staticmethod
    def resolve_items(parent: AplansPage, info, with_descendants) -> list[PageMenuItemNode | ExternalLinkMenuItemNode]:
        if not parent:
            return []
        plan = parent.plan
        if plan is None or not plan.is_visible_for_user(info.context.user):
            return []
        if with_descendants:
            pages = parent.get_descendants(inclusive=False)
        else:
            pages = parent.get_children()
        pages = pages.live().public().in_menu().specific()
        page_items = [PageMenuItemNode(page=page) for page in pages]
        links = plan.links
        external_link_items = [
            ExternalLinkMenuItemNode(url=link.url_i18n, link_text=link.title_i18n) for link in links.all()
        ]
        return page_items + external_link_items


class FooterNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'Footer'

    @staticmethod
    def resolve_items(parent: AplansPage | None, info, with_descendants) -> list[PageMenuItemNode]:
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
        footer_page_ids = [page.pk
                           for Model in AplansPage.get_subclasses()
                           for page in Model.objects.filter(show_in_footer=True)]
        pages = pages.filter(id__in=footer_page_ids).specific()
        return [PageMenuItemNode(page=page) for page in pages]


class AdditionalLinksNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'AdditionalLinks'

    @staticmethod
    def resolve_items(parent: AplansPage | None, info: GQLInfo, with_descendants: bool) -> list[PageMenuItemNode]:
        if not parent:
            return []
        if with_descendants:
            pages = parent.get_descendants(inclusive=False)
        else:
            pages = parent.get_children()
        pages = pages.live().public()
        # AplansPage is abstract and thus has no manager, so we need to find additional links pages for each subclass of
        # AplansPage individually. Gather IDs first and then make a separate query for additional_links_pages because
        # the latter gives us the correct order of the pages.

        additional_links_page_ids = [page.pk
                                     for Model in AplansPage.get_subclasses()
                                     for page in Model.objects.filter(show_in_additional_links=True)]
        pages = pages.filter(id__in=additional_links_page_ids).specific()

        # Add general additional links that should be included in all plan pages
        plan = parent.plan
        if plan is None:
            return []
        parent_plan = plan.parent

        if parent_plan is not None:
            cross_plan_page_ids = [
                page.pk for Model in AplansPage.get_subclasses()
                for page in Model.objects.filter(link_in_all_child_plans=True)
                if page.plan == parent_plan and parent_plan.is_visible_for_user(info.context.user)
            ]

            cross_plan_qs = WagtailPage.objects.get_queryset().filter(id__in=cross_plan_page_ids).specific()
            cross_plan_qs = cross_plan_qs.live().public()
            cross_plan_pages = [PageMenuItemNode(page=page, cross_plan_link=True) for page in cross_plan_qs]
        else:
            cross_plan_pages = []
        pages_nodes = [PageMenuItemNode(page=page) for page in pages]
        return pages_nodes + cross_plan_pages


class Query:
    plan_page = graphene.Field(PageInterface, plan=graphene.ID(required=True), path=graphene.String(required=True))

    def resolve_plan_page(self, info, plan, path, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None
        if not plan_obj.is_visible_for_user(info.context.user):
            return None

        root = plan_obj.get_translated_root_page()
        if root is None:
            return None
        if not path.endswith('/'):
            path = path + '/'
        qs = root.get_descendants(inclusive=True).live().public().filter(url_path=path).specific()
        return gql_optimizer.query(qs, info).first()
