from django.apps import AppConfig
from django.db.models import Q


_wagtail_get_pages_with_direct_explore_permission = None


def filter_plan_pages(user):
    from wagtail.core.models import Page

    pages = _wagtail_get_pages_with_direct_explore_permission(user)
    if user.is_superuser:
        pages = Page.objects.all()

    plan = user.get_active_admin_plan()
    if plan.root_page:
        # pages = pages.descendant_of(plan.root_page, inclusive=True)
        q = pages.descendant_of_q(plan.root_page, inclusive=True)
        for translation in plan.root_page.get_translations():
            q |= pages.descendant_of_q(translation, inclusive=True)
        # Do not exclude global root page (i.e., parent of plan.root_page), otherwise language switcher won't work
        q |= Q(depth=1)
        pages = pages.filter(q)

    return pages


def patch_wagtail_page_hierarchy():
    """Monkeypatch filtering pages by the currently active action plan."""
    from wagtail.admin import navigation

    global _wagtail_get_pages_with_direct_explore_permission

    _wagtail_get_pages_with_direct_explore_permission = navigation.get_pages_with_direct_explore_permission
    navigation.get_pages_with_direct_explore_permission = filter_plan_pages


def resolve_page_url_path(self, info):
    # Strip the trailing '/'
    return self.url_path.rstrip('/')


def patch_grapple_url_resolvers():
    from grapple.types.pages import PageInterface

    PageInterface.resolve_url_path = resolve_page_url_path


class PagesConfig(AppConfig):
    name = 'pages'

    def ready(self):
        patch_wagtail_page_hierarchy()
        patch_grapple_url_resolvers()
