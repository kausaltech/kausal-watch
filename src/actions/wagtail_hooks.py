from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.contrib.admin.utils import quote
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.search import SearchArea
from wagtail.admin.site_summary import SummaryItem
from wagtail.admin.views.home import UserObjectsInWorkflowModerationPanel, WorkflowObjectsToModeratePanel
from wagtail.models import TaskState, WorkflowState

from kausal_common.users import user_or_bust, user_or_none

from aplans.context_vars import get_admin_cache

from admin_site.wagtail import execute_admin_post_save_tasks

from . import pledge_participants_admin, wagtail_admin  # noqa: F401
from .bulk_approve import SKIP_LOG_ACTION
from .models import Action, ActionContactPerson, Plan
from .save_actions import ActionCreateAction, ActionEditAction

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.actions.registry import ActionRegistry
    from wagtail.admin.ui.components import Component
    from wagtail.log_actions import LogActionRegistry

    from laces.typing import RenderContext

    from aplans.types import WatchAdminRequest

    from actions.permission_policy import ActionPermissionPolicy
    from users.models import User


def _superuser_review_plan_ids(user: User) -> set[int]:
    """Return the plans a superuser reviews in: the active plan and those they administer or moderate in."""
    plan_ids: set[int] = set()
    if (active_plan := user.get_active_admin_plan(required=False)) is not None:
        plan_ids.add(active_plan.pk)
    if (person := user.get_corresponding_person()) is not None:
        plan_ids.update(person.general_admin_plans.values_list('pk', flat=True))
        moderated = ActionContactPerson.objects.filter(ActionContactPerson.moderators_q(), person=person)
        plan_ids.update(moderated.values_list('action__plan', flat=True))
    return plan_ids


WAGTAIL_SUBMISSIONS_HEADING = 'Your pages and snippets in a workflow'


def _with_plans(actions: list[Action]) -> list[Action]:
    plans = Plan.objects.in_bulk({action.plan_id for action in actions})
    for action in actions:
        action.plan = plans[action.plan_id]
    return actions


# How long an action may wait at a moderation step before it is labelled overdue
OVERDUE_AFTER = timedelta(days=14)


class RowLabelsMixin:
    """
    Label each listed action's title with Wagtail's status labels.

    The label names the action's plan when the actions are in several plans, and tells when it is overdue.
    """

    _row_labels: dict[str, list[tuple[str, str]]]

    def _label_rows(self, rows: list[tuple[Action, datetime | None]]) -> None:
        """Label the rows, given each action and when it started waiting for review at its current step."""
        several_plans = len({action.plan_id for action, _ in rows}) > 1
        overdue_since = timezone.now() - OVERDUE_AFTER
        self._row_labels = {}
        for action, waiting_since in rows:
            labels = []
            if several_plans:
                labels.append((action.plan.name_i18n, 'w-status--label'))
            if waiting_since is not None and waiting_since < overdue_since:
                labels.append((str(_('Overdue')), 'w-status--primary'))
            if labels:
                self._row_labels[action.get_admin_edit_url()] = labels

    def render_html(self, parent_context: RenderContext | None = None) -> str:
        html = super().render_html(parent_context)  # type: ignore[misc]
        for edit_url, labels in getattr(self, '_row_labels', {}).items():
            labels_html = ' '.join(
                render_to_string('wagtailadmin/shared/status_tag.html', {'label': text, 'classname': classname})
                for text, classname in labels
            )
            # The first link to the edit page is the row's title
            title_link = re.search(rf'<a href="{re.escape(edit_url)}"[^>]*>.*?</a>', html, re.DOTALL)
            if title_link is not None:
                html = f'{html[: title_link.end()]} {labels_html}{html[title_link.end() :]}'
        return mark_safe(html)  # noqa: S308


def _waiting_for_review_since(workflow_state: WorkflowState) -> datetime | None:
    task_state = workflow_state.current_task_state
    if task_state is None or task_state.status != TaskState.STATUS_IN_PROGRESS:
        return None
    return task_state.started_at


def _row_order(request: WatchAdminRequest, action: Action, waiting_since: datetime) -> tuple[bool, str, int, datetime]:
    """Group the rows by plan, the active plan first and the others by name, and within each the longest waiting first."""
    plan = action.plan
    return (plan.pk != request.get_active_admin_plan().pk, plan.name_i18n.casefold(), plan.pk, waiting_since)


class ActionsToModeratePanel(RowLabelsMixin, WorkflowObjectsToModeratePanel):
    """Wagtail's "Awaiting your review" panel for actions, across the user's plans with the active plan first."""

    order = 50

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:
        context = super().get_context_data(parent_context)
        request = parent_context['request']
        user = user_or_bust(request.user)
        states = [state for state in context['states'] if isinstance(state['obj'], Action)]
        _with_plans([state['obj'] for state in states])
        # Wagtail's group approval tasks list actions to their group's members regardless of plan
        policy = cast('ActionPermissionPolicy', Action.permission_policy())
        states = [state for state in states if policy.user_has_permission_in_own_plan(user, 'change', state['obj'])]
        if user.is_superuser:
            plan_ids = _superuser_review_plan_ids(user)
            states = [state for state in states if state['obj'].plan_id in plan_ids]
        self._label_rows([(state['obj'], state['task_state'].started_at) for state in states])
        for state in states:
            # A single step's progress would always be the same empty circle
            if len(state['workflow_tasks']) < 2:
                state['workflow_tasks'] = []
        context['states'] = sorted(states, key=lambda state: _row_order(request, state['obj'], state['task_state'].started_at))
        return context


class ActionsInModerationPanel(RowLabelsMixin, UserObjectsInWorkflowModerationPanel):
    """Wagtail's "Your items in moderation" panel for actions, across the user's plans with the active plan first."""

    order = 51

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:
        context = super().get_context_data(parent_context)
        request = parent_context['request']
        states = [state for state in context['workflow_states'] if isinstance(state.content_object, Action)]
        _with_plans([state.content_object for state in states])
        self._label_rows([(state.content_object, _waiting_for_review_since(state)) for state in states])
        context['workflow_states'] = sorted(
            states,
            key=lambda state: _row_order(request, state.content_object, state.current_task_state.started_at),
        )
        return context

    def render_html(self, parent_context: RenderContext | None = None) -> str:
        html = super().render_html(parent_context)
        # Wagtail's heading speaks of pages and snippets; its msgid is a variable so that makemessages leaves it out
        return mark_safe(  # noqa: S308
            html.replace(
                format_html('<span data-panel-heading-text>{}</span>', gettext(WAGTAIL_SUBMISSIONS_HEADING)),
                format_html('<span data-panel-heading-text>{}</span>', _('Your submissions in moderation')),
                1,
            )
        )


# Runs after the admin site's own hook, which removes Wagtail's unfiltered moderation panels
@hooks.register('construct_homepage_panels', order=500)
def add_action_moderation_panels(request: WatchAdminRequest, panels: list[Component]) -> None:
    if not settings.ENABLE_ACTION_MODERATION_UI:
        return
    panels.extend([ActionsToModeratePanel(), ActionsInModerationPanel()])


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


@hooks.register('register_actions')
def register_action_save_actions(registry: ActionRegistry) -> None:
    registry.register(Action, ActionCreateAction)
    registry.register(Action, ActionEditAction)


@hooks.register('register_log_actions')
def register_plan_log_actions(actions: LogActionRegistry):
    actions.register_action('plan.publish', _('Publish plan'), _('Plan published'))
    actions.register_action('plan.unpublish', _('Unpublish plan'), _('Plan unpublished'))
    actions.register_action(SKIP_LOG_ACTION, _('Skip moderation task'), _('Moderation task skipped'))


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
        reverse('wagtailsnippets_actions_action:list'),
        name='actions',
        icon_name='kausal-action',
        order=200,
    )


class BulkApproveMenuItem(MenuItem):
    def is_shown(self, request):
        user = user_or_none(request.user)
        if user is None:
            return False
        plan = get_admin_cache(request).plan
        if plan is None or plan.features.moderation_workflow is None:
            return False
        return user.is_superuser


@hooks.register('register_settings_menu_item')
def register_bulk_approve_menu_item():
    return BulkApproveMenuItem(
        _('Release actions from moderation'),
        reverse('wagtailsnippets_actions_action:bulk_approve_in_moderation'),
        icon_name='lock-open',
        order=210,
    )


@hooks.register('insert_global_admin_js')
def pledge_participants_admin_js():

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
