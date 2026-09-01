from __future__ import annotations

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from wagtail import hooks
from wagtail.models import Page, PagePermissionTester
from wagtail.snippets.models import register_snippet

from kausal_common.users import user_or_none

from admin_site.viewsets import (
    BaseChangeLogMessageCreateView,
    BaseChangeLogMessageDeleteView,
    BaseChangeLogMessageEditView,
    BaseChangeLogMessageViewSet,
)
from pages.models import AplansPage, PageChangeLogMessage, PlanRootPage, StaticPage


class VeryRestrictivePagePermissionTester(PagePermissionTester):
    def can_copy(self):
        return False

    def can_delete(self, ignore_bulk=False):
        return False

    def can_unpublish(self):
        return False


@hooks.register('construct_page_listing_buttons')
def restrict_more_button_permissions_very_much(buttons, page, user, context=None):
    if getattr(page, 'restrict_more_button_permissions_very_much', False):
        for button in buttons:
            if button.label == _('More'):
                button.page_perms = VeryRestrictivePagePermissionTester(user, page)


@hooks.register('construct_page_listing_buttons')
def remove_sort_menu_order_button(buttons, page, user, context=None):
    if getattr(page, 'remove_sort_menu_order_button', False):
        for button in buttons:
            if button.label == _('More'):
                button.dropdown_buttons = [b for b in button.dropdown_buttons if b.url != '?ordering=ord']


@hooks.register('construct_page_action_menu')
def remove_page_action_menu_items_except_publish(menu_items, request, context):
    if getattr(context.get('page'), 'remove_page_action_menu_items_except_publish', False):
        menu_items[:] = [i for i in menu_items if i.__class__.__name__ == 'PublishMenuItem']


@hooks.register('after_publish_page')
def redirect_to_change_log_after_publish(request, page):
    """Redirect to change log message creation after publishing a page."""

    # Only redirect for some page types (do not allow subclasses of StaticPage)
    if not isinstance(page.specific, PlanRootPage) and type(page.specific) is not StaticPage:
        return None

    # Check if the page's plan has change log enabled
    plan = page.specific.plan
    if not plan or not plan.features.enable_change_log:
        return None

    # Get the latest revision (the one that was just published)
    latest_revision = page.get_latest_revision()
    if not latest_revision:
        return None

    # Build the redirect URL with page and revision parameters
    change_log_create_url = reverse('wagtailsnippets_pages_pagechangelogmessage:add')
    redirect_url = f'{change_log_create_url}?page={page.pk}&revision={latest_revision.pk}'

    return HttpResponseRedirect(redirect_url)


class PageChangeLogMessageCreateView(BaseChangeLogMessageCreateView[PageChangeLogMessage, AplansPage]):
    related_field_name = 'page'
    success_url_name = 'wagtailadmin_explore_root'

    def get_related_object_by_pk(self, pk: str) -> Page | None:
        try:
            return Page.objects.get(pk=pk)
        except Page.DoesNotExist:
            return None

    def check_related_object_permission(self, related_obj: Page | None) -> bool:
        if related_obj is None:
            return False
        user = user_or_none(self.request.user)
        if user is None:
            return False
        page_perms = related_obj.permissions_for_user(user)
        return page_perms.can_edit()

    def get_revision_id(self) -> str | None:
        """Get revision ID from GET params or POST data (hidden field)."""
        if self.request.method == 'POST':
            return self.request.POST.get('revision')
        return self.request.GET.get('revision')

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        revision_id = self.get_revision_id()
        if revision_id:
            from wagtail.models import Revision

            revision = Revision.objects.filter(pk=revision_id).first()
            if revision:
                form.instance.revision = revision
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['revision_id'] = self.get_revision_id()
        return context


class PageChangeLogMessageEditView(BaseChangeLogMessageEditView[PageChangeLogMessage, AplansPage]):
    related_field_name = 'page'
    success_url_name = 'wagtailadmin_pages:edit'

    def check_related_object_permission(self, related_obj: Page | None) -> bool:
        if related_obj is None:
            return False
        user = user_or_none(self.request.user)
        if user is None:
            return False
        page_perms = related_obj.permissions_for_user(user)
        return page_perms.can_edit()


class PageChangeLogMessageDeleteView(BaseChangeLogMessageDeleteView[PageChangeLogMessage, AplansPage]):
    related_field_name = 'page'

    def check_related_object_permission(self, related_obj: Page | None) -> bool:
        if related_obj is None:
            return False
        user = user_or_none(self.request.user)
        if user is None:
            return False
        page_perms = related_obj.permissions_for_user(user)
        return page_perms.can_edit()


class PageChangeLogMessageViewSet(BaseChangeLogMessageViewSet[PageChangeLogMessage]):
    model = PageChangeLogMessage
    menu_label = pgettext_lazy('menu label', 'Page change history messages')
    plan_filter_path = 'plan'
    add_view_class = PageChangeLogMessageCreateView
    edit_view_class = PageChangeLogMessageEditView
    delete_view_class = PageChangeLogMessageDeleteView


register_snippet(PageChangeLogMessageViewSet)
