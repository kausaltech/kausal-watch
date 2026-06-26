from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.admin.utils import quote
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.search import SearchArea
from wagtail.admin.site_summary import SummaryItem

from kausal_common.users import user_or_none

from aplans.context_vars import get_admin_cache

from admin_site.wagtail import execute_admin_post_save_tasks

from . import pledge_participants_admin, wagtail_admin  # noqa: F401

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.log_actions import LogActionRegistry

    from laces.typing import RenderContext

    from aplans.types import WatchAdminRequest


class ActionsSummaryItem(SummaryItem):
    template_name = 'site_summary/actions.html'
    request: WatchAdminRequest

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:
        ctx = super().get_context_data(parent_context)
        assert ctx is not None
        plan = self.request.get_active_admin_plan()
        ctx['active_actions'] = plan.actions.get_queryset().active().count()
        ctx['plan'] = plan
        return ctx

    def is_shown(self):
        return True


@hooks.register('construct_homepage_summary_items', order=1001)
def add_actions_summary_item(request, items):
    items.append(ActionsSummaryItem(request))


@hooks.register('insert_editor_js')
def editor_js():
    return f'<script src="{static("actions/action-tasks-wagtail.js")}"></script>'


@hooks.register('after_edit_snippet')
def after_edit_snippet(request, snippet):
    execute_admin_post_save_tasks(snippet, request.user)


@hooks.register('register_log_actions')
def register_plan_log_actions(actions: LogActionRegistry):
    actions.register_action('plan.publish', _('Publish plan'), _('Plan published'))
    actions.register_action('plan.unpublish', _('Unpublish plan'), _('Plan unpublished'))


class ActionsSearchArea(SearchArea):
    def is_shown(self, request: HttpRequest) -> bool:
        user = user_or_none(request.user)
        if user is None:
            return False
        admin_cache = get_admin_cache(request)
        # FIXME: Replace with Action permission policy
        return user.can_access_admin(admin_cache.plan)


@hooks.register('register_admin_search_area')
def register_documents_search_area():
    return ActionsSearchArea(
        _('Actions'),
        reverse('actions_action_modeladmin_index'),
        name='actions',
        icon_name='kausal-action',
        order=200,
    )


@hooks.register('insert_global_admin_js')
def pledge_participants_admin_js():
    from django.utils.html import format_html

    return format_html('<script src="{}"></script>', static('admin_site/js/pledge_participants.js'))


@hooks.register('register_admin_urls')
def register_pledge_participants_urls():
    return pledge_participants_admin.get_pledge_participants_admin_urlpatterns()


@hooks.register('register_admin_menu_item')
def register_pledges_submenu():
    from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem

    from actions.pledge_admin import PledgeViewSet
    from actions.pledge_participants_admin import ParticipantsViewSet

    pledge_viewset = PledgeViewSet()
    participants_viewset = ParticipantsViewSet()

    pledges_url = reverse(pledge_viewset.get_url_name('list'))
    participants_url = reverse(participants_viewset.get_url_name('list'))

    submenu = Menu(
        items=[
            MenuItem(_('Pledges'), pledges_url, icon_name='kausal-pledge', order=1),
            MenuItem(_('Participants'), participants_url, icon_name='group', order=2),
        ]
    )

    class PledgesSubmenuItem(SubmenuMenuItem):
        def is_shown(self, request) -> bool:
            from users.models import User

            if not super().is_shown(request):
                return False
            user = request.user
            if not isinstance(user, User):
                return False
            plan = user.get_active_admin_plan(required=False)
            if plan is None:
                return False
            return plan.features.enable_community_engagement

    return PledgesSubmenuItem(
        _('Pledges'),
        submenu,
        icon_name='kausal-pledge',
        order=41,
    )


@hooks.register('construct_snippet_listing_buttons')
def remove_pledge_translate_listing_button(buttons, instance, _user):
    """
    Hide wagtail-localize "Translate" listing action for pledges.

    Pledge translations are managed via locale switching between existing locale copies.
    """
    from actions.models import Pledge

    if not isinstance(instance, Pledge):
        return

    translate_url = reverse(
        'wagtail_localize:submit_snippet_translation',
        args=[instance._meta.app_label, instance._meta.model_name, quote(instance.pk)],
    )
    buttons[:] = [button for button in buttons if getattr(button, 'url', None) != translate_url]
