import graphene
import graphene_django_optimizer as gql_optimizer
from wagtail.core.models import Page as WagtailPage
from grapple.types.pages import PageInterface

from aplans.graphql_types import get_plan_from_context
from pages.models import AplansPage


class MenuItemNode(graphene.ObjectType):
    class Meta:
        name = 'MenuItem'

    id = graphene.ID(required=True)
    page = graphene.Field(PageInterface, required=False)
    external_url = graphene.String(required=False)
    link_text = graphene.String(required=True)

    parent = graphene.Field('pages.schema.MenuItemNode')
    children = graphene.List('pages.schema.MenuItemNode')

    def resolve_id(parent, info):
        return parent.page.id

    def resolve_page(parent, info):
        if parent.page:
            return parent.page.specific
        return None

    def resolve_link_text(parent, info):
        if parent.page:
            assert not parent.link_text and not parent.external_url
            return parent.page.title
        return parent.link_text

    def resolve_parent(parent, info):
        parent = WagtailPage.objects.parent_of(parent.page).specific().first()
        if parent is None:
            return
        return MenuItemNode(page=parent)

    def resolve_children(parent, info):
        pages = parent.page.get_children().live().public()
        # TODO: Get rid of this terrible hack
        if 'footer' in info.path:
            footer_page_ids = [page.id
                               for Model in AplansPage.get_subclasses()
                               for page in Model.objects.filter(show_in_footer=True)]
            pages = pages.filter(id__in=footer_page_ids)
        pages = pages.specific()
        return [MenuItemNode(page=page) for page in pages]


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
        page_items = [MenuItemNode(page=page) for page in pages]
        links = parent.plan.links
        external_link_items = [
            MenuItemNode(external_url=link.url_i18n, link_text=link.title_i18n) for link in links.all()
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
        return [MenuItemNode(page=page) for page in pages]


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
