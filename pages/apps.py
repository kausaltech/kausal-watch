import typing
from django.apps import AppConfig
from django.conf import settings
from wagtailorderable.signals import post_reorder

if typing.TYPE_CHECKING:
    from wagtail.models import Page


def get_site_by_plan(user):
    plan = user.get_active_admin_plan()
    if not plan:
        return None, None

    root_page = plan.root_page
    if root_page:
        root_site = root_page.get_site()
    else:
        root_site = None
    return root_site, root_page


def resolve_page_url_path(self, info):
    # Strip the trailing '/'
    return self.url_path.rstrip('/')


def resolve_parent(self: 'Page', info, **kwargs):
    from pages.models import PlanRootPage
    if isinstance(self.specific, PlanRootPage):
        return None
    parent = self.get_parent()
    if parent is None or parent.depth == 1:
        return None
    return parent.specific


def resolve_siblings(self, info, **kwargs):
    return []


def resolve_ancestors(self, info, **kwargs):
    from grapple.utils import resolve_queryset

    qs = self.get_ancestors().live().public().specific()
    qs = qs.filter(depth__gt=2)
    return resolve_queryset(qs, info, **kwargs)


def patch_grapple_url_resolvers():
    from grapple.types.pages import PageInterface

    PageInterface.resolve_url_path = resolve_page_url_path
    PageInterface.resolve_parent = resolve_parent
    PageInterface.resolve_siblings = resolve_siblings
    PageInterface.resolve_next_siblings = resolve_siblings
    PageInterface.resolve_previous_siblings = resolve_siblings
    PageInterface.resolve_ancestors = resolve_ancestors


def post_reorder_categories(sender, **kwargs):
    from actions.models import CategoryType
    qs = kwargs['queryset']
    type_ids = qs.values_list('type_id')
    for category_type in CategoryType.objects.filter(id__in=type_ids, synchronize_with_pages=True):
        category_type.synchronize_pages()


class PagesConfig(AppConfig):
    name = 'pages'

    def ready(self):
        from actions.category_admin import CategoryAdmin
        patch_grapple_url_resolvers()
        post_reorder.connect(
            post_reorder_categories, sender=CategoryAdmin, dispatch_uid='reorder_category_pages'
        )
