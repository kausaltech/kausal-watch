import graphene
import graphene_django_optimizer as gql_optimizer
from wagtail.models import Page as WagtailPage
from grapple.types.pages import PageInterface

from aplans.graphql_types import get_plan_from_context, register_graphene_node
from pages.models import AplansPage


@register_graphene_node
class PageMenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'PageMenuItem'

    id = graphene.ID(required=True)
    page = graphene.Field(PageInterface, required=True)
    parent = graphene.Field('pages.schema.PageMenuItemNode')
    children = graphene.List('pages.schema.PageMenuItemNode')

    def resolve_id(item, info):
        return item.page.id

    def resolve_parent(item, info):
        if not item.page:
            return None
        parent = WagtailPage.objects.parent_of(item.page).specific().first()
        if parent is None:
            return None
        return PageMenuItemNode(page=parent)

    def resolve_children(item, info):
        pages = item.page.get_children().live().public()
        # TODO: Get rid of this terrible hack
        if 'footer' in info.path.as_list():
            footer_page_ids = [page.id
                               for Model in AplansPage.get_subclasses()
                               for page in Model.objects.filter(show_in_footer=True)]
            pages = pages.filter(id__in=footer_page_ids)
        pages = pages.specific()
        return [PageMenuItemNode(page=page) for page in pages]


@register_graphene_node
class ExternalLinkMenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'ExternalLinkMenuItem'

    url = graphene.String(required=True)
    link_text = graphene.String(required=True)


class MenuItem(graphene.Union):
    class Meta:
        types = (PageMenuItemNode, ExternalLinkMenuItemNode)


class MenuNodeMixin():
    """
    Mixin for main menu and footer

    You need to provide a `resolve_items(parent, info, with_descendants)` method when you use this mixin.

    It's a mixin instead of a base class because Graphene turns resolver methods into static methods and we can thus
    not use polymorphism in resolver methods.
    https://docs.graphene-python.org/en/latest/types/objecttypes/#resolverimplicitstaticmethod
    """
    items = graphene.List(MenuItem, required=True, with_descendants=graphene.Boolean(default_value=False))

    @classmethod
    def resolver_from_plan(cls, plan, info):
        root_page = plan.get_translated_root_page()
        if root_page is None:
            return None
        return root_page.specific

    @classmethod
    def create_plan_menu_field(cls):
        return graphene.Field(cls, resolver=cls.resolver_from_plan)


class MainMenuNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'MainMenu'

    def resolve_items(parent, info, with_descendants):
        if not parent:
            return []
        if with_descendants:
            pages = parent.get_descendants(inclusive=False)
        else:
            pages = parent.get_children()
        pages = pages.live().public().in_menu().specific()
        page_items = [PageMenuItemNode(page=page) for page in pages]
        links = parent.plan.links
        external_link_items = [
            ExternalLinkMenuItemNode(url=link.url_i18n, link_text=link.title_i18n) for link in links.all()
        ]
        return page_items + external_link_items


class FooterNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'Footer'

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
        return [PageMenuItemNode(page=page) for page in pages]


class AdditionalLinksNode(MenuNodeMixin, graphene.ObjectType):
    class Meta:
        name = 'AdditionalLinks'

    def resolve_items(parent, info, with_descendants):
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
        additional_links_page_ids = [page.id
                                     for Model in AplansPage.get_subclasses()
                                     for page in Model.objects.filter(show_in_additional_links=True)]
        pages = pages.filter(id__in=additional_links_page_ids).specific()
        return [PageMenuItemNode(page=page) for page in pages]


class Query:
    plan_page = graphene.Field(PageInterface, plan=graphene.ID(required=True), path=graphene.String(required=True))

    def resolve_plan_page(self, info, plan, path, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        root = plan_obj.get_translated_root_page()
        if not path.endswith('/'):
            path = path + '/'
        qs = root.get_descendants(inclusive=True).live().public().filter(url_path=path).specific()
        return gql_optimizer.query(qs, info).first()
