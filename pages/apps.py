from django.apps import AppConfig


_wagtail_get_pages_with_direct_explore_permission = None


def filter_plan_pages(user):
    from wagtail.core.models import Page

    pages = _wagtail_get_pages_with_direct_explore_permission(user)
    if user.is_superuser:
        pages = Page.objects.all()

    plan = user.get_active_admin_plan()
    if plan.root_page:
        pages = pages.descendant_of(plan.root_page, inclusive=True)

    return pages


def patch_wagtail_page_hierarchy():
    """Monkeypatch filtering pages by the currently active action plan."""
    from wagtail.admin import navigation

    global _wagtail_get_pages_with_direct_explore_permission

    _wagtail_get_pages_with_direct_explore_permission = navigation.get_pages_with_direct_explore_permission
    navigation.get_pages_with_direct_explore_permission = filter_plan_pages


class PagesConfig(AppConfig):
    name = 'pages'

    def ready(self):
        patch_wagtail_page_hierarchy()
